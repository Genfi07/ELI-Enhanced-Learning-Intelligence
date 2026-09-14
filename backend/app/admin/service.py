"""Lógica de negocio del panel de admin.

Reglas de seguridad implementadas aquí:
  - Un admin NO puede modificarse a sí mismo el rol.
  - Un admin NO puede eliminarse a sí mismo.
  - Solo un SUPER_ADMIN puede degradar a otro SUPER_ADMIN.
  - Solo un SUPER_ADMIN puede eliminar usuarios.
  - Cada cambio genera una entrada de audit_logs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import record_audit
from app.config import dynamic
from app.db.models.conversation import Conversation
from app.db.models.document import Document
from app.db.models.memory import Memory
from app.db.models.message import Message
from app.db.models.role import Role
from app.db.models.system import AuditLog
from app.db.models.tool import ToolCall
from app.db.models.trace import RequestTrace
from app.db.models.user import User
from app.observability.logging import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
async def list_users(
    session: AsyncSession,
    *,
    status: str | None = None,
    role: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    if status:
        stmt = stmt.where(User.status == status)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            (func.lower(User.email).like(like))
            | (func.lower(User.name).like(like))
        )
    if role:
        stmt = stmt.join(Role, User.role_id == Role.id).where(Role.name == role)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.scalars(stmt)).all())


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


async def change_user_role(
    session: AsyncSession,
    *,
    actor: User,
    target_id: uuid.UUID,
    new_role_name: str,
    request: Request | None,
) -> User:
    if target_id == actor.id:
        raise HTTPException(
            status_code=400, detail="No puedes cambiar tu propio rol"
        )

    target = await get_user(session, target_id)

    # Solo SUPER_ADMIN puede tocar a otro SUPER_ADMIN
    current_role_name = target.role.name if target.role else "USER"
    if current_role_name == "SUPER_ADMIN" and actor.role.name != "SUPER_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Solo un SUPER_ADMIN puede modificar a otro SUPER_ADMIN",
        )

    new_role = await session.scalar(
        select(Role).where(Role.name == new_role_name)
    )
    if new_role is None:
        raise HTTPException(status_code=400, detail="Rol inválido")

    before = {"role": current_role_name}
    target.role_id = new_role.id
    after = {"role": new_role_name}

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="user.change_role",
        entity_type="user",
        entity_id=str(target.id),
        before=before,
        after=after,
        request=request,
    )
    await session.flush()
    await session.refresh(target, ["role"])
    return target


async def block_user(
    session: AsyncSession,
    *,
    actor: User,
    target_id: uuid.UUID,
    reason: str | None,
    request: Request | None,
) -> User:
    if target_id == actor.id:
        raise HTTPException(status_code=400, detail="No puedes bloquearte a ti mismo")

    target = await get_user(session, target_id)

    if target.role and target.role.name == "SUPER_ADMIN" and actor.role.name != "SUPER_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Solo un SUPER_ADMIN puede bloquear a otro SUPER_ADMIN",
        )

    before = {"status": target.status}
    target.status = "BLOCKED"
    after = {"status": "BLOCKED"}

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="user.block",
        entity_type="user",
        entity_id=str(target.id),
        before=before,
        after=after,
        meta={"reason": reason} if reason else None,
        request=request,
    )
    await session.flush()
    return target


async def unblock_user(
    session: AsyncSession,
    *,
    actor: User,
    target_id: uuid.UUID,
    request: Request | None,
) -> User:
    target = await get_user(session, target_id)
    before = {"status": target.status}
    target.status = "ACTIVE"
    after = {"status": "ACTIVE"}

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="user.unblock",
        entity_type="user",
        entity_id=str(target.id),
        before=before,
        after=after,
        request=request,
    )
    await session.flush()
    return target


async def soft_delete_user(
    session: AsyncSession,
    *,
    actor: User,
    target_id: uuid.UUID,
    request: Request | None,
) -> User:
    if target_id == actor.id:
        raise HTTPException(
            status_code=400, detail="No puedes eliminarte a ti mismo"
        )
    target = await get_user(session, target_id)

    if target.role and target.role.name == "SUPER_ADMIN" and actor.role.name != "SUPER_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Solo un SUPER_ADMIN puede eliminar a otro SUPER_ADMIN",
        )

    before = {"status": target.status, "email": target.email}
    target.status = "DELETED"
    after = {"status": "DELETED"}

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="user.delete",
        entity_type="user",
        entity_id=str(target.id),
        before=before,
        after=after,
        request=request,
    )
    await session.flush()
    return target


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
async def set_setting(
    session: AsyncSession,
    *,
    actor: User,
    key: str,
    value: Any,
    category: str | None,
    description: str | None,
    request: Request | None,
) -> None:
    # Validación: no permitir modificar secretos vía endpoint admin
    if key in ("secret_key", "openai_api_key", "google_client_secret",
               "tavily_api_key", "database_url"):
        raise HTTPException(
            status_code=400,
            detail="Esta clave no se puede modificar desde el panel. Usa variables de entorno.",
        )

    # Valor anterior (para audit)
    old = await dynamic.get_dynamic(key, default=None)

    await dynamic.set_dynamic_setting(
        key,
        value,
        category=category or "general",
        description=description,
        updated_by=actor.id,
    )

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="config.update",
        entity_type="setting",
        entity_id=key,
        before={"value": old},
        after={"value": value},
        request=request,
    )
    await session.flush()


async def delete_setting(
    session: AsyncSession,
    *,
    actor: User,
    key: str,
    request: Request | None,
) -> None:
    old = await dynamic.get_dynamic(key, default=None)
    removed = await dynamic.delete_dynamic_setting(key)
    if not removed:
        raise HTTPException(status_code=404, detail="Override no encontrado")

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="config.delete_override",
        entity_type="setting",
        entity_id=key,
        before={"value": old},
        after=None,
        request=request,
    )
    await session.flush()


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
async def list_audit_logs(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if actor_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.scalars(stmt)).all())


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
# Precio aproximado de OpenAI gpt-4o-mini: $0.15/1M input + $0.60/1M output
_PRICE_INPUT_PER_M = 0.15
_PRICE_OUTPUT_PER_M = 0.60


async def _count(session: AsyncSession, stmt) -> int:
    return int(await session.scalar(stmt) or 0)


async def get_analytics_overview(session: AsyncSession) -> dict[str, Any]:
    users_total = await _count(session, select(func.count()).select_from(User))
    users_active = await _count(
        session,
        select(func.count()).select_from(User).where(User.status == "ACTIVE"),
    )
    users_blocked = await _count(
        session,
        select(func.count()).select_from(User).where(User.status == "BLOCKED"),
    )
    conversations = await _count(
        session, select(func.count()).select_from(Conversation)
    )
    messages = await _count(session, select(func.count()).select_from(Message))
    memories = await _count(
        session,
        select(func.count()).select_from(Memory).where(Memory.status == "ACTIVE"),
    )
    documents = await _count(session, select(func.count()).select_from(Document))
    tool_calls = await _count(session, select(func.count()).select_from(ToolCall))
    errors = await _count(
        session,
        select(func.count()).select_from(RequestTrace).where(RequestTrace.status == "error"),
    )

    # Tokens: suma sobre mensajes assistant (los que tienen tokens_in/out)
    tok_in, tok_out = (await session.execute(
        select(
            func.coalesce(func.sum(Message.tokens_in), 0),
            func.coalesce(func.sum(Message.tokens_out), 0),
        )
    )).one()
    tok_in = int(tok_in or 0)
    tok_out = int(tok_out or 0)
    total_tokens = tok_in + tok_out
    cost_estimate = (
        (tok_in / 1_000_000) * _PRICE_INPUT_PER_M
        + (tok_out / 1_000_000) * _PRICE_OUTPUT_PER_M
    )

    return {
        "users_total": users_total,
        "users_active": users_active,
        "users_blocked": users_blocked,
        "conversations_total": conversations,
        "messages_total": messages,
        "memories_total": memories,
        "documents_total": documents,
        "tool_calls_total": tool_calls,
        "tokens_total": total_tokens,
        "cost_estimate_usd": round(cost_estimate, 4),
        "errors_total": errors,
    }


async def get_timeseries(
    session: AsyncSession, *, days: int = 7
) -> list[dict[str, Any]]:
    """Serie diaria de mensajes, tokens y errores para los últimos N días."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day = func.date_trunc("day", Message.created_at).label("day")

    # Mensajes + tokens por día
    stmt_msgs = (
        select(
            day,
            func.count().label("msgs"),
            func.coalesce(func.sum(Message.tokens_in + Message.tokens_out), 0).label("toks"),
        )
        .where(Message.created_at >= since)
        .group_by(day)
        .order_by(day)
    )
    rows_msgs = (await session.execute(stmt_msgs)).all()
    msg_by_day = {
        r.day.date().isoformat(): (int(r.msgs), int(r.toks)) for r in rows_msgs
    }

    # Errores por día
    day_t = func.date_trunc("day", RequestTrace.created_at).label("day")
    stmt_err = (
        select(day_t, func.count().label("errs"))
        .where(RequestTrace.created_at >= since, RequestTrace.status == "error")
        .group_by(day_t)
        .order_by(day_t)
    )
    rows_err = (await session.execute(stmt_err)).all()
    err_by_day = {r.day.date().isoformat(): int(r.errs) for r in rows_err}

    # Rellenar días faltantes
    points = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        key = d.isoformat()
        msgs, toks = msg_by_day.get(key, (0, 0))
        points.append(
            {
                "date": key,
                "messages": msgs,
                "tokens": toks,
                "errors": err_by_day.get(key, 0),
            }
        )
    return points