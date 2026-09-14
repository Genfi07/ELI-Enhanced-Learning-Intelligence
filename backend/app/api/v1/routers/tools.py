"""Endpoints de gestión y ejecución de herramientas.

Endpoints:
  GET  /tools                          → lista tools disponibles para el usuario
  GET  /tools/calls                    → historial de invocaciones del usuario
  POST /tools/{name}/invoke            → invoca una tool
  GET  /tools/pending-actions          → acciones esperando confirmación
  POST /tools/pending-actions/{id}/confirm → confirma y ejecuta
  POST /tools/pending-actions/{id}/reject  → rechaza
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.core.schemas.tool import (
    PendingActionOut,
    ToolCallOut,
    ToolInvokeIn,
    ToolInvokeOut,
    ToolOut,
)
from app.db.models.tool import PendingAction, ToolCall
from app.db.models.user import User
from app.observability.logging import get_logger
from app.tools.autonomy import get_user_autonomy_level
from app.tools.registry import build_registry
from app.tools.runtime import ToolInvocationContext, build_runtime

log = get_logger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


def _runtime():
    return build_runtime()


def _registry():
    return build_registry()


# --------------------------------------------------------------------------- #
# Listar tools
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[ToolOut])
async def list_tools(
    user: User = Depends(current_user),
) -> list[ToolOut]:
    """Lista las tools registradas. No filtra por permisos del usuario:
    el runtime decidirá si puede invocarlas. La UI puede mostrarlas todas
    para que el usuario sepa qué existe.
    """
    registry = _registry()
    return [ToolOut.from_manifest(m) for m in registry.all_manifests()]


# --------------------------------------------------------------------------- #
# Historial de llamadas
# --------------------------------------------------------------------------- #
@router.get("/calls", response_model=list[ToolCallOut])
async def list_tool_calls(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[ToolCallOut]:
    stmt = (
        select(ToolCall)
        .where(ToolCall.user_id == user.id)
        .order_by(ToolCall.created_at.desc())
        .limit(limit)
    )
    rows = list((await session.scalars(stmt)).all())
    return [ToolCallOut.from_model(r) for r in rows]


# --------------------------------------------------------------------------- #
# Invocar
# --------------------------------------------------------------------------- #
@router.post("/{tool_name}/invoke", response_model=ToolInvokeOut)
async def invoke_tool(
    tool_name: str,
    body: ToolInvokeIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> ToolInvokeOut:
    runtime = _runtime()
    context = ToolInvocationContext(
        user_id=user.id,
        conversation_id=body.conversation_id,
        message_id=None,
    )
    result = await runtime.invoke(
        session,
        user=user,
        tool_name=tool_name,
        arguments=body.arguments,
        context=context,
    )
    await session.commit()
    return result


# --------------------------------------------------------------------------- #
# Pending actions
# --------------------------------------------------------------------------- #
@router.get("/pending-actions", response_model=list[PendingActionOut])
async def list_pending_actions(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[PendingActionOut]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(PendingAction)
        .where(
            PendingAction.user_id == user.id,
            PendingAction.status == "PENDING",
            PendingAction.expires_at > now,
        )
        .order_by(PendingAction.created_at.desc())
    )
    rows = list((await session.scalars(stmt)).all())
    return [PendingActionOut.from_model(p) for p in rows]


@router.post(
    "/pending-actions/{pending_id}/confirm",
    response_model=ToolInvokeOut,
)
async def confirm_pending(
    pending_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> ToolInvokeOut:
    pending = await _load_pending(session, user, pending_id)
    if pending.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"la acción ya está en estado {pending.status}",
        )
    if pending.expires_at <= datetime.now(timezone.utc):
        pending.status = "EXPIRED"
        await session.commit()
        raise HTTPException(status_code=410, detail="la acción ha expirado")

    runtime = _runtime()
    result = await runtime.execute_pending(session, pending=pending, user=user)
    await session.commit()
    return result


@router.post(
    "/pending-actions/{pending_id}/reject",
    response_model=PendingActionOut,
)
async def reject_pending(
    pending_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> PendingActionOut:
    pending = await _load_pending(session, user, pending_id)
    if pending.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"la acción ya está en estado {pending.status}",
        )
    pending.status = "REJECTED"
    await session.commit()
    await session.refresh(pending)
    return PendingActionOut.from_model(pending)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _load_pending(
    session: AsyncSession,
    user: User,
    pending_id: uuid.UUID,
) -> PendingAction:
    stmt = select(PendingAction).where(
        PendingAction.id == pending_id,
        PendingAction.user_id == user.id,
    )
    pending = await session.scalar(stmt)
    if pending is None:
        raise HTTPException(status_code=404, detail="Acción no encontrada")
    return pending