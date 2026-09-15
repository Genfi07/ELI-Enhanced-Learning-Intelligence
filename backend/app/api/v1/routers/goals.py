"""Endpoints REST para las metas propias de ELI.

Permisos:
  - GET (listar/ver): cualquier usuario autenticado.
  - POST / PATCH / DELETE (crear, editar, cambiar estado): solo admins
    (permiso admin.panel). Coherente con la política: solo Genfi
    controla las metas de ELI desde fuera del chat.

Patrón de persistencia:
  - El servicio (GoalService) hace flush() para asignar IDs y validar.
  - El router hace commit() explícito y refresh() del objeto para cargar
    las columnas generadas por BD (created_at, updated_at) antes de
    serializar. Mismo patrón que memory.py.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.auth.rbac import require_permission
from app.db.models.user import User
from app.eli.goal_schemas import (
    GoalCreateIn,
    GoalNoteIn,
    GoalOut,
    GoalUpdateIn,
)
from app.eli.goal_service import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalOut])
async def list_goals(
    status_filter: str | None = Query(default=None, alias="status"),
    kind: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[GoalOut]:
    svc = GoalService(session)
    goals = await svc.list_goals(
        status=status_filter, kind=kind, limit=limit
    )
    return [GoalOut.from_model(g) for g in goals]


@router.get("/{goal_id}", response_model=GoalOut)
async def get_goal(
    goal_id: uuid.UUID,
    _: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> GoalOut:
    svc = GoalService(session)
    goal = await svc.get_by_id(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    return GoalOut.from_model(goal)


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    body: GoalCreateIn,
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> GoalOut:
    svc = GoalService(session)
    goal = await svc.create_goal(
        kind=body.kind,
        content=body.content,
        origin="TAUGHT",
        priority=body.priority,
        related_topics=body.related_topics,
    )
    await svc.pause_lowest_priority_if_too_many()
    await session.commit()
    await session.refresh(goal)
    return GoalOut.from_model(goal)


@router.patch("/{goal_id}", response_model=GoalOut)
async def update_goal(
    goal_id: uuid.UUID,
    body: GoalUpdateIn,
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> GoalOut:
    svc = GoalService(session)
    goal = await svc.get_by_id(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Meta no encontrada")

    if body.status is not None:
        goal = await svc.update_status(goal_id, body.status)
    if body.priority is not None:
        goal = await svc.update_priority(goal_id, body.priority)
    if body.content is not None:
        goal.content = body.content.strip()
        await session.flush()

    await session.commit()
    if goal is None:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    await session.refresh(goal)
    return GoalOut.from_model(goal)


@router.post("/{goal_id}/notes", response_model=GoalOut)
async def add_note(
    goal_id: uuid.UUID,
    body: GoalNoteIn,
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> GoalOut:
    svc = GoalService(session)
    goal = await svc.add_progress_note(goal_id, body.note)
    if goal is None:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    await session.commit()
    await session.refresh(goal)
    return GoalOut.from_model(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def abandon_goal(
    goal_id: uuid.UUID,
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> None:
    svc = GoalService(session)
    goal = await svc.update_status(goal_id, "ABANDONED")
    if goal is None:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    await session.commit()