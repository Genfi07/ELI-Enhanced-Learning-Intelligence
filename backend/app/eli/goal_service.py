"""GoalService: gestiona las metas propias de ELI.

Responsabilidades:
  - Crear metas (automáticas, enseñadas o detectadas por patrón).
  - Listar metas por estado.
  - Pausar, reanudar, marcar cumplidas o abandonar.
  - Añadir notas de progreso.
  - Construir el bloque <goals> que se inyecta en el system prompt.

Reglas de diseño (modo A - totalmente automático):
  - ELI crea sus propias metas sin pedir aprobación.
  - No hay límite duro de metas activas.
  - Si hay >15 activas, se emite una advertencia para que ELI misma
    decida pausar las de menor prioridad.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eli_goal import EliGoal
from app.observability.logging import get_logger

log = get_logger(__name__)


VALID_KINDS = ("LEARN", "EXPLORE", "IMPROVE", "CONNECT", "PROPOSE")
VALID_ORIGINS = ("SELF", "TAUGHT", "DETECTED")
VALID_STATUSES = ("ACTIVE", "PAUSED", "ACHIEVED", "ABANDONED")

# Aviso suave cuando hay demasiadas metas activas.
SOFT_LIMIT_ACTIVE = 15


class GoalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Crear
    # ------------------------------------------------------------------ #
    async def create_goal(
        self,
        *,
        kind: str,
        content: str,
        origin: str = "SELF",
        priority: int = 3,
        related_topics: list[str] | None = None,
        source_conversation_id: uuid.UUID | None = None,
        detected_pattern: str | None = None,
    ) -> EliGoal:
        kind = kind.upper().strip()
        origin = origin.upper().strip()
        if kind not in VALID_KINDS:
            raise ValueError(f"kind inválido: {kind}")
        if origin not in VALID_ORIGINS:
            raise ValueError(f"origin inválido: {origin}")

        goal = EliGoal(
            kind=kind,
            content=content.strip(),
            origin=origin,
            priority=max(1, min(5, priority)),
            status="ACTIVE",
            related_topics=related_topics or [],
            source_conversation_id=source_conversation_id,
            detected_pattern=detected_pattern,
        )
        self.session.add(goal)
        await self.session.flush()

        log.info(
            "eli_goal_created",
            goal_id=str(goal.id),
            kind=kind,
            origin=origin,
            priority=goal.priority,
        )
        return goal

    # ------------------------------------------------------------------ #
    # Lectura
    # ------------------------------------------------------------------ #
    async def get_by_id(self, goal_id: uuid.UUID) -> EliGoal | None:
        return await self.session.get(EliGoal, goal_id)

    async def list_goals(
        self,
        *,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[EliGoal]:
        stmt = select(EliGoal)
        if status is not None:
            stmt = stmt.where(EliGoal.status == status)
        if kind is not None:
            stmt = stmt.where(EliGoal.kind == kind)
        stmt = stmt.order_by(
            EliGoal.priority.desc(),
            EliGoal.created_at.desc(),
        ).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def list_active(self, limit: int = 50) -> list[EliGoal]:
        return await self.list_goals(status="ACTIVE", limit=limit)

    async def count_active(self) -> int:
        stmt = select(func.count()).select_from(EliGoal).where(
            EliGoal.status == "ACTIVE"
        )
        return await self.session.scalar(stmt) or 0

    # ------------------------------------------------------------------ #
    # Cambios de estado
    # ------------------------------------------------------------------ #
    async def update_status(
        self, goal_id: uuid.UUID, status: str
    ) -> EliGoal | None:
        status = status.upper().strip()
        if status not in VALID_STATUSES:
            raise ValueError(f"status inválido: {status}")

        goal = await self.get_by_id(goal_id)
        if goal is None:
            return None

        goal.status = status
        goal.updated_at = datetime.now(timezone.utc)
        if status == "ACHIEVED":
            goal.achieved_at = datetime.now(timezone.utc)
        elif status == "ABANDONED":
            goal.abandoned_at = datetime.now(timezone.utc)

        await self.session.flush()
        log.info(
            "eli_goal_status_changed",
            goal_id=str(goal_id),
            new_status=status,
        )
        return goal

    async def update_priority(
        self, goal_id: uuid.UUID, priority: int
    ) -> EliGoal | None:
        goal = await self.get_by_id(goal_id)
        if goal is None:
            return None
        goal.priority = max(1, min(5, priority))
        goal.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return goal

    async def add_progress_note(
        self, goal_id: uuid.UUID, note: str
    ) -> EliGoal | None:
        goal = await self.get_by_id(goal_id)
        if goal is None:
            return None

        notes = list(goal.progress_notes or [])
        notes.append(
            {
                "text": note.strip(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        goal.progress_notes = notes
        goal.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return goal

    # ------------------------------------------------------------------ #
    # Pausar metas de baja prioridad si hay demasiadas
    # ------------------------------------------------------------------ #
    async def pause_lowest_priority_if_too_many(self) -> EliGoal | None:
        """Si hay más de SOFT_LIMIT_ACTIVE metas activas, pausa la de
        menor prioridad (más antigua si empatan). Devuelve la pausada o None.
        """
        active_count = await self.count_active()
        if active_count <= SOFT_LIMIT_ACTIVE:
            return None

        stmt = (
            select(EliGoal)
            .where(EliGoal.status == "ACTIVE")
            .order_by(EliGoal.priority.asc(), EliGoal.created_at.asc())
            .limit(1)
        )
        goal = await self.session.scalar(stmt)
        if goal is None:
            return None

        goal.status = "PAUSED"
        goal.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        log.info(
            "eli_goal_auto_paused",
            goal_id=str(goal.id),
            reason="demasiadas metas activas",
        )
        return goal

    # ------------------------------------------------------------------ #
    # Bloque para el system prompt
    # ------------------------------------------------------------------ #
    async def build_goals_block(self) -> str:
        """Bloque <goals> con las metas activas para inyectar en el prompt.

        Si no hay metas activas, devuelve un bloque vacío corto (con una
        nota que indica que no tiene metas propias todavía).
        """
        active = await self.list_active(limit=20)

        if not active:
            return (
                "<goals>\n"
                "Ahora mismo no tienes metas propias activas. "
                "Puedes proponer una cuando detectes un tema recurrente "
                "o cuando algo te resulte genuinamente interesante.\n"
                "</goals>"
            )

        lines = ["<goals>"]
        lines.append(f"Tienes {len(active)} meta(s) activa(s):")
        lines.append("")
        for g in active:
            notes_count = len(g.progress_notes or [])
            lines.append(
                f"- [{g.kind}, prioridad {g.priority}, origen {g.origin}] "
                f"{g.content}"
                + (f" ({notes_count} nota(s) de progreso)" if notes_count else "")
            )
        lines.append("")
        lines.append(
            "INSTRUCCIÓN: estas son tus metas propias. Puedes mencionarlas "
            "si encajan con la conversación, avanzar en ellas cuando sea "
            "pertinente, o proponer pausarlas si ya no tienen sentido. No "
            "las impongas: son tuyas, no de quien te habla."
        )
        lines.append("</goals>")
        return "\n".join(lines)