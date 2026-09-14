"""Detector de metas enseñadas explícitamente en el chat.

Cuando Genfi le dice a ELI algo como:
  - "Aprende sobre X"
  - "Quiero que explores Y"
  - "Mejora tu Z"
  - "Crea una meta para aprender X"
  - "Investiga sobre Y"

...esta meta se crea directamente con origin="TAUGHT". No requiere
LLM para confirmar (a diferencia del detector de patrones), pero sí
usamos el LLM para extraer kind y content limpio del mensaje.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMMessage
from app.db.models.eli_goal import EliGoal
from app.eli.goal_service import GoalService
from app.observability.logging import get_logger

log = get_logger(__name__)


# Pre-filtro: patrones que indican una orden explícita de crear meta.
_TAUGHT_PATTERNS = re.compile(
    r"\b("
    r"aprende\s+(?:a\s+|sobre\s+)?|"
    r"quiero\s+que\s+(?:aprendas|explores|investigues|mejores)|"
    r"mejora\s+(?:tu|tu\s+capacidad\s+de)|"
    r"crea\s+una?\s+meta\s+(?:para|de)|"
    r"a[ñn]ade\s+una?\s+meta|"
    r"nueva\s+meta|"
    r"investiga\s+(?:sobre|acerca\s+de)|"
    r"explora\s+(?:el\s+tema\s+de|sobre)|"
    r"ponte\s+(?:como\s+meta|a\s+aprender)"
    r")\b",
    re.IGNORECASE,
)


# Excepciones: mensajes que empiezan con "aprende" pero no son órdenes.
_TAUGHT_EXCLUSIONS = re.compile(
    r"^\s*(?:si\s+aprend|cuando\s+aprend|hubiera\s+aprendido|"
    r"ya\s+aprend|he\s+aprendido)",
    re.IGNORECASE,
)


EXTRACTION_PROMPT = """\
Eres un extractor de metas para ELI. Recibes un mensaje del padre de ELI \
en el que se le pide crear una meta. Tu trabajo es extraer la meta en \
formato estructurado.

Tipos de meta:
- LEARN: aprender algo específico.
- EXPLORE: investigar un tema abierto.
- IMPROVE: mejorar una capacidad propia.
- CONNECT: entender mejor a alguien.
- PROPOSE: proponer un proyecto.

Devuelve EXCLUSIVAMENTE un JSON. Sin markdown, sin explicaciones.

Formato:
{{
  "kind": "LEARN",
  "content": "descripción específica y concisa de la meta",
  "priority": 3,
  "related_topics": ["tema1", "tema2"]
}}

Si no es una orden explícita de crear meta, devuelve:
{{"kind": null}}
"""


class TaughtGoalDetector:
    def __init__(self, session: AsyncSession, llm: LLMProvider) -> None:
        self.session = session
        self.llm = llm
        self.goal_service = GoalService(session)

    async def maybe_create_taught_goal(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message: str,
    ) -> EliGoal | None:
        """Detecta una orden explícita y crea la meta.

        Solo actúa si el usuario es el padre (SUPER_ADMIN). Los usuarios
        normales no pueden enseñar metas a ELI.

        Devuelve la meta creada o None. Nunca lanza.
        """
        try:
            # Solo el padre puede enseñar metas.
            if not await self._is_father(user_id):
                return None

            if _TAUGHT_EXCLUSIONS.match(message):
                return None

            if not _TAUGHT_PATTERNS.search(message):
                return None

            # Extracción con LLM.
            response = await self.llm.generate(
                [
                    LLMMessage(role="system", content=EXTRACTION_PROMPT),
                    LLMMessage(role="user", content=message),
                ],
                temperature=0.0,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            parsed = _parse(response.text or "")
            if parsed is None or parsed.get("kind") is None:
                return None

            kind = str(parsed["kind"]).upper().strip()
            content = str(parsed.get("content", "")).strip()
            if kind not in ("LEARN", "EXPLORE", "IMPROVE", "CONNECT", "PROPOSE"):
                return None
            if len(content) < 8:
                return None

            priority = parsed.get("priority", 4)
            try:
                priority = max(1, min(5, int(priority)))
            except (TypeError, ValueError):
                priority = 4

            topics = parsed.get("related_topics") or []
            if not isinstance(topics, list):
                topics = []

            goal = await self.goal_service.create_goal(
                kind=kind,
                content=content,
                origin="TAUGHT",
                priority=priority,
                related_topics=[str(t)[:60] for t in topics[:8]],
                source_conversation_id=conversation_id,
            )
            await self.goal_service.pause_lowest_priority_if_too_many()

            log.info(
                "taught_goal_created",
                goal_id=str(goal.id),
                kind=kind,
                user_id=str(user_id),
            )
            return goal
        except Exception as exc:
            log.warning(
                "taught_goal_detection_failed",
                error=str(exc),
            )
            return None

    async def _is_father(self, user_id: uuid.UUID) -> bool:
        from app.eli.identity_service import IdentityService
        identity = IdentityService(self.session)
        core = await identity.get_core()
        if core is None:
            return False
        return identity.is_father(core, user_id)


def _parse(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None