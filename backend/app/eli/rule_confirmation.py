"""Procesa la confirmación o el rechazo de una propuesta de regla pendiente.

Diseño:
  - Solo actúa si el usuario es Genfi y hay una propuesta PENDING en la
    conversación actual.
  - Detecta si el mensaje del usuario es una confirmación ("sí", "vale",
    "guárdala") o un rechazo ("no", "cancela", "olvídalo").
  - SI detecta: ejecuta la acción en BD (crear EliRule o marcar REJECTED).
    Los efectos secundarios ocurren AQUÍ, no dependen del LLM.
  - Devuelve un bloque de contexto que ELI leerá para saber qué responder.

Regla de diseño clave:
  El LLM narra. El código ejecuta. Nunca al revés.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eli_identity import EliRule, EliRuleProposal
from app.eli.identity_service import IdentityService
from app.observability.logging import get_logger

log = get_logger(__name__)


Decision = Literal["confirm", "reject"]


# Longitud máxima del mensaje para considerarlo una confirmación. Si es más
# largo, probablemente contiene más contexto y no es una confirmación simple.
_MAX_CONFIRM_LEN = 80

# Marcadores afirmativos. Anclados al inicio del mensaje.
_AFFIRM_RE = re.compile(
    r"^\s*(?:"
    r"s[íi]\b|"
    r"sip\b|"
    r"claro\b|"
    r"vale\b|"
    r"ok(?:ay|ey)?\b|"
    r"perfecto\b|"
    r"genial\b|"
    r"adelante\b|"
    r"confirm\w*|"
    r"dale\b|"
    r"h[áa]zlo\b|"
    r"gu[áa]rdal[ao]\b|"
    r"por\s+supuesto\b|"
    r"de\s+acuerdo\b|"
    r"as[íi]\s+es\b|"
    r"aplic[áa]l[ao]\b"
    r")",
    re.IGNORECASE,
)

# Marcadores negativos. Anclados al inicio del mensaje.
_REJECT_RE = re.compile(
    r"^\s*(?:"
    r"no\b|"
    r"nel\b|"
    r"nop\b|"
    r"cancel\w*|"
    r"descarta\w*|"
    r"desc[áa]rta\w*|"
    r"olv[íi]da\w*|"
    r"d[ée]ja\w*|"
    r"rechaza\w*|"
    r"rech[áa]za\w*|"
    r"no\s+lo\s+gu[áa]rdes|"
    r"no\s+la\s+gu[áa]rdes"
    r")",
    re.IGNORECASE,
)

# Excepciones: mensajes que empiezan con un marcador pero NO son la decisión.
_NOT_A_DECISION_RE = re.compile(
    r"^\s*no\s+(?:s[ée]|estoy|creo|pienso|sab[íi]a|tengo\s+idea)\b",
    re.IGNORECASE,
)


def detect_confirmation(message: str) -> Decision | None:
    """Devuelve "confirm", "reject" o None si no es una decisión clara.

    Función pura. No toca BD.
    """
    text = message.strip()
    if not text or len(text) > _MAX_CONFIRM_LEN:
        return None

    # Casos que empiezan con "no" pero no son un rechazo
    if _NOT_A_DECISION_RE.match(text):
        return None

    # Rechazo primero (más específico: "no, no la guardes")
    if _REJECT_RE.match(text):
        return "reject"

    if _AFFIRM_RE.match(text):
        return "confirm"

    return None


class RuleConfirmationProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.identity = IdentityService(session)

    # ------------------------------------------------------------------ #
    # API principal
    # ------------------------------------------------------------------ #
    async def maybe_process(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message: str,
    ) -> dict[str, Any] | None:
        """Si el mensaje es una confirmación/rechazo y hay propuesta pendiente,
        ejecuta la acción y devuelve un dict con el bloque de contexto y
        metadatos. Si no aplica, devuelve None.
        """
        # 1) Solo el padre
        core = await self.identity.get_core()
        if core is None or not self.identity.is_father(core, user_id):
            return None

        # 2) ¿Es una confirmación o un rechazo?
        decision = detect_confirmation(message)
        if decision is None:
            return None

        # 3) ¿Hay propuesta pendiente en esta conversación?
        proposal = await self._get_pending(conversation_id)
        if proposal is None:
            return None

        # 4) Ejecutar
        if decision == "confirm":
            rule = await self._confirm(proposal, user_id)
            block = (
                "<rule_confirmation_result>\n"
                "Estado: CONFIRMADA\n"
                f"Categoría: {rule.category}\n"
                f"Contenido: {rule.content}\n"
                "La regla se ha guardado en tu sistema y está ahora activa. "
                "INSTRUCCIÓN: Confirma brevemente al usuario que la regla "
                "se ha guardado y quedará activa desde este momento.\n"
                "</rule_confirmation_result>"
            )
            return {
                "decision": "confirm",
                "proposal_id": str(proposal.id),
                "rule_id": str(rule.id),
                "category": rule.category,
                "content": rule.content,
                "block": block,
            }

        # decision == "reject"
        await self._reject(proposal)
        block = (
            "<rule_confirmation_result>\n"
            "Estado: RECHAZADA\n"
            f"Contenido: {proposal.content}\n"
            "La propuesta ha sido descartada y no se aplicará. "
            "INSTRUCCIÓN: Confirma brevemente al usuario que la propuesta "
            "se ha descartado y sigue con normalidad.\n"
            "</rule_confirmation_result>"
        )
        return {
            "decision": "reject",
            "proposal_id": str(proposal.id),
            "content": proposal.content,
            "block": block,
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _get_pending(
        self, conversation_id: uuid.UUID
    ) -> EliRuleProposal | None:
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

    async def _confirm(
        self, proposal: EliRuleProposal, user_id: uuid.UUID
    ) -> EliRule:
        now = datetime.now(timezone.utc)
        rule = EliRule(
            category=proposal.category,
            content=proposal.content,
            priority=50,
            taught_by=proposal.taught_by,
            confirmed_by=user_id,
            active=True,
        )
        self.session.add(rule)
        await self.session.flush()

        proposal.status = "CONFIRMED"
        proposal.resolved_at = now
        proposal.confirmed_rule_id = rule.id

        log.info(
            "rule_proposal_confirmed",
            proposal_id=str(proposal.id),
            rule_id=str(rule.id),
            category=rule.category,
        )
        return rule

    async def _reject(self, proposal: EliRuleProposal) -> None:
        now = datetime.now(timezone.utc)
        proposal.status = "REJECTED"
        proposal.resolved_at = now
        log.info(
            "rule_proposal_rejected",
            proposal_id=str(proposal.id),
        )