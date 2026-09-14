"""GoalDetector: detecta metas propias analizando conversaciones.

Estrategia híbrida (dos fases):
  Fase 1 — Pre-filtro por keywords.
    Mira el último mensaje del usuario. Si no contiene ningún tema
    sustantivo (técnico, científico, hobby, profesional), se salta.
    Ahorra ~95% de llamadas al LLM en conversaciones triviales.

  Fase 2 — Confirmación por LLM.
    Si el pre-filtro pasa, se envían los últimos N mensajes al LLM con
    un prompt estructurado. El LLM decide si crear una meta y cuál.

Cuándo corre:
  - Cada 10 turnos de la conversación.
  - O cuando llega un mensaje del usuario >= 200 caracteres que además
    contiene algún tema sustantivo.

Modo de operación:
  - "Modo A": totalmente automático. ELI crea metas sin pedir aprobación.
  - Las metas creadas llevan origin="DETECTED" y source_conversation_id.
  - Deduplicación: si hay una meta activa con contenido similar, se salta.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMMessage
from app.db.models.eli_goal import EliGoal
from app.db.session import session_scope
from app.eli.goal_service import GoalService
from app.observability.logging import get_logger

log = get_logger(__name__)


# Cada cuántos turnos se ejecuta el análisis periódico.
DETECT_EVERY_N_TURNS = 10

# Longitud mínima de mensaje para disparar análisis inmediato.
LONG_MESSAGE_THRESHOLD = 200

# Cuántos mensajes recientes enviar al LLM.
RECENT_MESSAGES_WINDOW = 20


# Marcadores de temas sustantivos. Si el mensaje contiene alguno,
# vale la pena llamar al LLM. Si no, se descarta el análisis.
_TOPIC_HINTS = re.compile(
    r"\b("
    # Tecnología
    r"python|javascript|typescript|rust|golang|java|kotlin|swift|"
    r"react|vue|angular|next\.?js|node|fastapi|django|flask|"
    r"sql|postgres|mysql|mongo|redis|docker|kubernetes|"
    r"api|rest|graphql|websocket|oauth|jwt|"
    r"machine\s+learning|ml|ia|llm|rag|embedding|transformer|"
    r"algoritmo|funci[oó]n|clase|m[eé]todo|variable|array|objeto|"
    # Ciencia / conocimiento
    r"f[ií]sica|qu[ií]mica|biolog[ií]a|matem[aá]tica|estad[ií]stica|"
    r"historia|filosof[ií]a|psicolog[ií]a|econom[ií]a|"
    # Actividades / hobbies
    r"f[uú]tbol|baloncesto|tenis|ajedrez|guitarra|piano|"
    r"cocina|receta|viaje|libro|pel[ií]cula|serie|"
    # Profesiones / roles
    r"desarrollador|programador|ingenier[oa]|dise[nñ]ador|"
    r"estudiante|profesor|m[eé]dico|abogado|"
    r"trabajo|proyecto|empresa|startup|cliente|"
    # Educación
    r"aprender|estudiar|entender|investigar|mejorar|"
    r"curso|tutorial|documentaci[oó]n|manual"
    r")\b",
    re.IGNORECASE,
)


# Cola de tareas de fondo para no ser recolectados por el GC.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def has_topic_hints(text: str) -> bool:
    """Pre-filtro rápido: ¿hay algún tema sustantivo en el texto?"""
    return bool(_TOPIC_HINTS.search(text))


def should_run_detector(
    *,
    message: str,
    turns_since_last_detect: int,
) -> bool:
    """Decide si toca ejecutar el detector en este turno.

    Condiciones (cualquiera de las dos basta):
      - Han pasado >= 10 turnos desde el último análisis.
      - El mensaje es largo (>=200 chars) Y contiene temas sustantivos.
    """
    if turns_since_last_detect >= DETECT_EVERY_N_TURNS:
        return True
    if len(message) >= LONG_MESSAGE_THRESHOLD and has_topic_hints(message):
        return True
    return False


DETECTOR_PROMPT = """\
Eres un analizador de metas propias para ELI, una asistente de IA con \
identidad, memoria y estado interno. Recibes una conversación reciente \
entre una persona y ELI. Tu trabajo es decidir si hay un tema recurrente \
o un interés fuerte que justifique que ELI se proponga una meta propia.

Tipos de meta permitidos:
- LEARN: aprender algo específico (una tecnología, un concepto, un área).
- EXPLORE: investigar un tema abierto, sin objetivo definido.
- IMPROVE: mejorar una capacidad de ELI (razonamiento, estilo, memoria).
- CONNECT: entender mejor a la persona con la que habla.
- PROPOSE: proponer un proyecto o idea relacionada con lo que hablan.

Reglas ESTRICTAS:
1. Solo propones meta si hay evidencia CLARA y recurrente. Si no, no creas.
2. Una meta debe ser específica. "Aprender Python" es vaga. "Entender \
decoradores y context managers en Python" es específica.
3. La prioridad es 1-5. 3 es media. 4-5 solo si el interés es muy fuerte.
4. No propongas metas triviales ni que se cumplan en un turno.
5. NO dupliques metas que ya están en la lista de metas activas.

Metas activas actuales (no dupliques):
{active_goals}

Devuelve EXCLUSIVAMENTE un JSON. Sin markdown, sin explicaciones.

Si hay meta que crear:
{{
  "should_create": true,
  "kind": "LEARN",
  "content": "descripción específica",
  "priority": 3,
  "related_topics": ["tema1", "tema2"],
  "reason": "por qué (1 frase corta)"
}}

Si NO hay meta que crear:
{{
  "should_create": false,
  "reason": "por qué no (1 frase corta)"
}}
"""


class GoalDetector:
    def __init__(self, session: AsyncSession, llm: LLMProvider) -> None:
        self.session = session
        self.llm = llm
        self.goal_service = GoalService(session)

    # ------------------------------------------------------------------ #
    # API principal
    # ------------------------------------------------------------------ #
    async def maybe_create_goal(
        self, *, conversation_id: uuid.UUID
    ) -> EliGoal | None:
        """Analiza la conversación y crea una meta si procede.

        Devuelve la meta creada o None. Nunca lanza.
        """
        try:
            messages = await self._load_recent_messages(conversation_id)
            if not messages:
                return None

            # Concatenado para el pre-filtro.
            aggregate = " ".join(m.content for m in messages)
            if not has_topic_hints(aggregate):
                log.debug(
                    "goal_detector_no_topic_hints",
                    conversation_id=str(conversation_id),
                )
                return None

            prompt = await self._build_prompt(messages)
            response = await self.llm.generate(
                [
                    LLMMessage(role="user", content=prompt),
                ],
                temperature=0.3,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            candidate = self._parse_response(response.text or "")
            if candidate is None or not candidate.get("should_create"):
                return None

            # Deduplicación: evitar crear metas con contenido similar.
            if await self._is_duplicate(candidate["content"]):
                log.info(
                    "goal_detector_duplicate_skipped",
                    content=candidate["content"][:80],
                )
                return None

            goal = await self.goal_service.create_goal(
                kind=candidate["kind"],
                content=candidate["content"],
                origin="DETECTED",
                priority=int(candidate.get("priority", 3)),
                related_topics=candidate.get("related_topics") or [],
                source_conversation_id=conversation_id,
                detected_pattern=candidate.get("reason"),
            )
            # Auto-pausa si hay demasiadas activas (regla blanda).
            await self.goal_service.pause_lowest_priority_if_too_many()
            return goal
        except Exception as exc:
            log.warning(
                "goal_detector_failed",
                conversation_id=str(conversation_id),
                error=str(exc),
            )
            return None

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _load_recent_messages(self, conversation_id: uuid.UUID):
        from app.db.models.message import Message

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(RECENT_MESSAGES_WINDOW)
        )
        rows = list((await self.session.scalars(stmt)).all())
        rows.reverse()
        return rows

    async def _build_prompt(self, messages) -> str:
        transcript_lines = []
        for m in messages:
            role = "Usuario" if m.role == "user" else "ELI"
            transcript_lines.append(f"{role}: {m.content}")
        transcript = "\n".join(transcript_lines)

        active = await self.goal_service.list_active(limit=20)
        if active:
            active_str = "\n".join(f"- [{g.kind}] {g.content}" for g in active)
        else:
            active_str = "(ninguna)"

        return (
            DETECTOR_PROMPT.format(active_goals=active_str)
            + "\n\nCONVERSACIÓN RECIENTE:\n"
            + transcript
        )

    def _parse_response(self, raw: str) -> dict[str, Any] | None:
        payload = _extract_json(raw)
        if payload is None:
            return None

        if not isinstance(payload, dict):
            return None

        if not payload.get("should_create"):
            return None

        # Validar campos obligatorios.
        kind = str(payload.get("kind", "")).upper().strip()
        content = str(payload.get("content", "")).strip()
        if kind not in ("LEARN", "EXPLORE", "IMPROVE", "CONNECT", "PROPOSE"):
            return None
        if len(content) < 10:
            return None

        priority = payload.get("priority", 3)
        try:
            priority = max(1, min(5, int(priority)))
        except (TypeError, ValueError):
            priority = 3

        topics = payload.get("related_topics") or []
        if not isinstance(topics, list):
            topics = []

        return {
            "should_create": True,
            "kind": kind,
            "content": content,
            "priority": priority,
            "related_topics": [str(t)[:60] for t in topics[:8]],
            "reason": str(payload.get("reason", ""))[:200],
        }

    async def _is_duplicate(self, content: str, threshold: float = 0.6) -> bool:
        """Compara contra metas activas por solapamiento de palabras.

        Si el Jaccard de palabras significativas es >= threshold, se
        considera duplicado.
        """
        content_words = _significant_words(content)
        if not content_words:
            return False

        active = await self.goal_service.list_active(limit=50)
        for goal in active:
            goal_words = _significant_words(goal.content)
            if not goal_words:
                continue
            inter = content_words & goal_words
            union = content_words | goal_words
            jaccard = len(inter) / len(union) if union else 0.0
            if jaccard >= threshold:
                return True
        return False


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "a", "al", "y", "o", "u", "que", "qué",
    "es", "son", "está", "están", "para", "por", "con", "sin",
    "sobre", "entre", "como", "más", "menos", "muy", "mucho",
    "aprender", "explorar", "mejorar", "entender",
}


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"\b[a-záéíóúñ]{4,}\b", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# Tarea de fondo
# --------------------------------------------------------------------------- #
async def _run_detection_bg(
    provider: LLMProvider,
    conversation_id: uuid.UUID,
) -> None:
    try:
        async with session_scope() as session:
            detector = GoalDetector(session, provider)
            goal = await detector.maybe_create_goal(conversation_id=conversation_id)
            if goal is not None:
                log.info(
                    "goal_detector_created",
                    goal_id=str(goal.id),
                    kind=goal.kind,
                    priority=goal.priority,
                )
    except Exception as exc:
        log.warning("goal_detector_bg_failed", error=str(exc))


def schedule_detection(
    provider: LLMProvider, conversation_id: uuid.UUID
) -> None:
    """Lanza el detector en background. No bloquea el turno."""
    _spawn(_run_detection_bg(provider, conversation_id))