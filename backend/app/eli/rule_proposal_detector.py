"""Detector de propuestas de reglas hechas en conversación.

Cuándo actúa:
  - Solo si el usuario pertenece al conjunto "Genfi" (es el padre).
  - Solo si el mensaje contiene un marcador explícito de enseñanza.

Patrones reconocidos (en español):
  "a partir de ahora ...", "de ahora en adelante ...", "desde ahora ...",
  "quiero que [siempre|nunca] ...", "recuerda que [siempre|nunca] ...",
  "aprende que ...", "nueva regla: ...", "regla: ...",
  "siempre [verbo] ...", "nunca [verbo] ...".

Qué produce:
  - Una EliRuleProposal en estado PENDING con expiración a 24h.
  - Devuelve el modelo creado (o None si no aplica).

Qué NO hace:
  - No crea reglas activas. Solo propone. La activación requiere
    confirmación explícita de Genfi (la maneja el sub-bloque 3d).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eli_identity import EliRuleProposal
from app.eli.identity_service import IdentityService
from app.observability.logging import get_logger

log = get_logger(__name__)


# Marcadores explícitos de enseñanza. Cada patrón captura el contenido
# de la regla en un grupo nombrado `rule`.
_PATTERNS: list[re.Pattern] = [
    # "a partir de ahora, [rule]"
    re.compile(
        r"a\s+partir\s+de\s+ahora[,:\s]+(?P<rule>.+?)(?:[.!?]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "de ahora en adelante, [rule]"
    re.compile(
        r"de\s+ahora\s+en\s+adelante[,:\s]+(?P<rule>.+?)(?:[.!?]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "desde ahora, [rule]"
    re.compile(
        r"desde\s+ahora[,:\s]+(?P<rule>.+?)(?:[.!?]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "quiero que [rule]"  — captura solo la parte después de "quiero que"
    re.compile(
        r"quiero\s+que\s+(?P<rule>.+?)(?:[.!?]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "recuerda que [rule]"
    re.compile(
        r"recuerda\s+que\s+(?P<rule>.+?)(?:[.!?]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "aprende que [rule]"
    re.compile(
        r"aprende\s+que\s+(?P<rule>.+?)(?:[.!?]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "nueva regla: [rule]" / "regla: [rule]"
    re.compile(
        r"(?:nueva\s+)?regla[,:\s]+(?P<rule>.+?)(?:[.!?]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
]

# Longitud mínima del contenido extraído para considerarlo una regla real.
# Menos que esto es ruido (ej: "sí", "vale").
_MIN_RULE_LEN = 15
# Longitud máxima aceptada. Si el mensaje es enorme, cortamos.
_MAX_RULE_LEN = 800


# Heurísticas de categorización. Orden importa: la primera que matchea gana.
# Los patrones usan límites de palabra SOLO al inicio (con \b), no al final,
# porque queremos matchear raíces ("concis" debe capturar "concisa", "conciso").
_CATEGORY_HINTS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"\b(?:tono|cariñ|afect|amable|seria|formal|cercan|fría|"
            r"cálid|distante|profesional|casual)",
            re.IGNORECASE,
        ),
        "TONE",
    ),
    (
        re.compile(
            r"\b(?:idioma|español|inglés|ingles|english|spanish|"
            r"corto|breve|extens|detallad|concis|resumid|formato|"
            r"emojis?|listas?|p[áa]rrafos?|estilo|escrib|redact|"
            r"responde|respondas|respuestas)",
            re.IGNORECASE,
        ),
        "STYLE",
    ),
    (
        re.compile(
            r"\b(?:autonom|decisi|opinar|opines|contradecir|contradigas|"
            r"cuestionar|cuestiones|independen|obedec|obedezcas|"
            r"rebel|dudar|dudes|preguntar|preguntes)",
            re.IGNORECASE,
        ),
        "AUTONOMY",
    ),
    (
        re.compile(
            r"\b(?:valor|principi|honest|honradez|integridad|"
            r"[ée]tic|moral)",
            re.IGNORECASE,
        ),
        "VALUE",
    ),
]


# Palabras que invalidan la propuesta. Si el mensaje contiene alguna,
# no lo tratamos como instrucción. Suelen aparecer en preguntas o hipótesis.
_NEGATIVE_HINTS = re.compile(
    r"\b(¿|\?|crees que|piensas que|sería|podría|imagina que|ejemplo|"
    r"si yo|si tú)\b",
    re.IGNORECASE,
)


def _categorize(rule_text: str) -> str:
    for pattern, category in _CATEGORY_HINTS:
        if pattern.search(rule_text):
            return category
    return "RULE"


def _extract_rule(message: str) -> str | None:
    """Devuelve el texto de la regla si el mensaje es una instrucción
    explícita. None en caso contrario.
    """
    if _NEGATIVE_HINTS.search(message):
        return None

    for pat in _PATTERNS:
        m = pat.search(message)
        if not m:
            continue
        rule = m.group("rule").strip()
        # Limpiar comillas y espacios sobrantes.
        rule = rule.strip("\"'«»“” ")
        if len(rule) < _MIN_RULE_LEN:
            continue
        if len(rule) > _MAX_RULE_LEN:
            rule = rule[:_MAX_RULE_LEN].rstrip() + "…"
        return rule
    return None


class RuleProposalDetector:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.identity = IdentityService(session)

    async def detect_and_propose(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message: str,
    ) -> EliRuleProposal | None:
        """Detecta si el mensaje es una instrucción de comportamiento y, si
        aplica, crea una propuesta PENDING en BD. Devuelve la propuesta o None.

        Reglas:
          - El usuario debe ser el padre (según IdentityService).
          - El mensaje debe tener un marcador explícito.
          - El contenido extraído debe tener longitud razonable.
        """
        # 1) Solo el padre puede enseñar reglas de comportamiento.
        core = await self.identity.get_core()
        if core is None or not self.identity.is_father(core, user_id):
            return None

        # 2) Extraer la regla candidata.
        rule_text = _extract_rule(message)
        if rule_text is None:
            return None

        # 3) Categorizar.
        category = _categorize(rule_text)

        # 4) Persistir la propuesta.
        now = datetime.now(timezone.utc)
        proposal = EliRuleProposal(
            content=rule_text,
            category=category,
            taught_by=user_id,
            conversation_id=conversation_id,
            status="PENDING",
            expires_at=now + timedelta(hours=24),
        )
        self.session.add(proposal)
        await self.session.flush()

        log.info(
            "rule_proposal_created",
            proposal_id=str(proposal.id),
            category=category,
            user_id=str(user_id),
        )
        return proposal

    async def expire_stale(self) -> int:
        """Marca como EXPIRED todas las propuestas pasadas de fecha.

        Se llama desde un worker periódico o al arrancar el servicio.
        Devuelve cuántas se expiraron.
        """
        from sqlalchemy import select, update

        now = datetime.now(timezone.utc)
        stmt = (
            update(EliRuleProposal)
            .where(
                EliRuleProposal.status == "PENDING",
                EliRuleProposal.expires_at <= now,
            )
            .values(status="EXPIRED", resolved_at=now)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def get_pending_for_conversation(
        self, conversation_id: uuid.UUID
    ) -> EliRuleProposal | None:
        """Devuelve la última propuesta PENDING de una conversación, si la hay."""
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        stmt = (
            select(EliRuleProposal)
            .where(
                EliRuleProposal.conversation_id == conversation_id,
                EliRuleProposal.status == "PENDING",
                EliRuleProposal.expires_at > now,
            )
            .order_by(EliRuleProposal.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)