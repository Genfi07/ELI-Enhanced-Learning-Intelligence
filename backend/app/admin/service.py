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
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import record_audit
from app.config import dynamic
from app.db.models.conversation import Conversation
from app.db.models.document import Document
from app.db.models.memory import Memory
from app.db.models.message import Message
from app.db.models.role import Role
from app.db.models.system import AuditLog, SystemSetting
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


async def reset_all_settings(
    session: AsyncSession,
    *,
    actor: User,
    request: Request | None,
) -> int:
    """Borra todos los overrides de configuración.

    SystemSetting SOLO contiene overrides (los defaults viven en
    app.config.settings.Settings), así que un DELETE total es seguro.
    Devuelve cuántos overrides se eliminaron. La acción queda auditada.
    """
    total = (
        await session.scalar(
            select(func.count()).select_from(SystemSetting)
        )
    ) or 0

    if total == 0:
        return 0

    await session.execute(delete(SystemSetting))

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="settings.reset_all",
        entity_type="setting",
        entity_id="*",
        before={"overrides_count": total},
        after={"overrides_count": 0},
        request=request,
    )
    await session.flush()
    dynamic.invalidate_dynamic_cache()
    return total


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


# --------------------------------------------------------------------------- #
# Create user + promote to super
# --------------------------------------------------------------------------- #
async def create_user(
    session: AsyncSession,
    *,
    actor: User,
    name: str,
    email: str,
    password: str,
    role_name: str,
    request: Request | None,
) -> User:
    """Crea un usuario nuevo. Solo SUPER_ADMIN puede crear SUPER_ADMINs."""
    if role_name == "SUPER_ADMIN" and actor.role.name != "SUPER_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Solo un SUPER_ADMIN puede crear otro SUPER_ADMIN",
        )

    email_lc = email.strip().lower()
    exists = await session.scalar(
        select(User).where(func.lower(User.email) == email_lc)
    )
    if exists is not None:
        raise HTTPException(
            status_code=409, detail="Ya existe un usuario con ese email"
        )

    role = await session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise HTTPException(status_code=400, detail="Rol inválido")

    from app.auth.passwords import hash_password

    user = User(
        id=uuid.uuid4(),
        name=name.strip(),
        email=email_lc,
        password_hash=hash_password(password),
        role_id=role.id,
        status="ACTIVE",
    )
    session.add(user)
    await session.flush()

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="user.create",
        entity_type="user",
        entity_id=str(user.id),
        before=None,
        after={"email": email_lc, "name": name.strip(), "role": role_name},
        request=request,
    )
    await session.flush()
    await session.refresh(user, ["role"])
    return user


async def promote_to_super_admin(
    session: AsyncSession,
    *,
    actor: User,
    target_id: uuid.UUID,
    request: Request | None,
) -> User:
    """Promociona un usuario al rol SUPER_ADMIN. Solo un SUPER_ADMIN puede."""
    if actor.role.name != "SUPER_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Solo un SUPER_ADMIN puede promover a otro SUPER_ADMIN",
        )
    if target_id == actor.id:
        raise HTTPException(status_code=400, detail="Ya eres SUPER_ADMIN")

    target = await get_user(session, target_id)
    if target.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail=f"No se puede promover a un usuario en estado {target.status}",
        )

    current = target.role.name if target.role else "USER"
    if current == "SUPER_ADMIN":
        raise HTTPException(status_code=400, detail="Ya es SUPER_ADMIN")

    super_role = await session.scalar(
        select(Role).where(Role.name == "SUPER_ADMIN")
    )
    if super_role is None:
        raise HTTPException(
            status_code=500, detail="Rol SUPER_ADMIN no existe en la BD"
        )

    before = {"role": current}
    target.role_id = super_role.id
    after = {"role": "SUPER_ADMIN"}

    await record_audit(
        session,
        actor_user_id=actor.id,
        action="user.promote_to_super",
        entity_type="user",
        entity_id=str(target.id),
        before=before,
        after=after,
        request=request,
    )
    await session.flush()
    await session.refresh(target, ["role"])
    return target


# --------------------------------------------------------------------------- #
# Config guide
# --------------------------------------------------------------------------- #
async def get_config_guide(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Devuelve la guía de cada clave conocida, con su categoría real.

    Combina la guía estática (app.admin.config_guide.CONFIG_GUIDE) con la
    categoría dinámica que ya usa /admin/config para agrupar.
    """
    from app.admin.config_guide import CONFIG_GUIDE

    all_settings = await dynamic.list_all_settings_with_metadata()
    out: list[dict[str, Any]] = []
    for s in all_settings:
        key = s["key"]
        guide = CONFIG_GUIDE.get(key)
        if guide is None:
            continue
        out.append(
            {
                "key": key,
                "category": s["category"],
                "short": guide.get("short", ""),
                "description": guide.get("description", ""),
                "values": guide.get("values"),
                "impact": guide.get("impact"),
                "example": guide.get("example"),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# A2 — Conversaciones, mensajes y stats por usuario
# --------------------------------------------------------------------------- #
_PRICE_INPUT_PER_M_A2 = 0.15
_PRICE_OUTPUT_PER_M_A2 = 0.60


def _conversation_msg_count_subq():
    """Subquery que devuelve, por conversación, cuántos mensajes tiene.

    Se usa en lugar de un GROUP BY para evitar conflictos con el JOIN
    implícito a roles que SQLAlchemy mete por el relationship User.role.
    """
    return (
        select(
            Message.conversation_id.label("conversation_id"),
            func.count(Message.id).label("messages_count"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )


async def list_user_conversations(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Conversaciones de un usuario, con conteo de mensajes y datos del dueño."""
    counts_sq = _conversation_msg_count_subq()
    stmt = (
        select(
            Conversation,
            User,
            func.coalesce(counts_sq.c.messages_count, 0).label("messages_count"),
        )
        .join(User, User.id == Conversation.user_id)
        .outerjoin(
            counts_sq, counts_sq.c.conversation_id == Conversation.id
        )
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    out: list[dict[str, Any]] = []
    for conv, owner, count in rows:
        out.append(
            {
                "id": conv.id,
                "user_id": conv.user_id,
                "user_email": owner.email,
                "user_name": owner.name,
                "title": conv.title,
                "model": conv.model,
                "status": conv.status,
                "messages_count": int(count or 0),
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
            }
        )
    return out


async def list_all_conversations(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Todas las conversaciones de la plataforma, con filtros opcionales."""
    counts_sq = _conversation_msg_count_subq()
    stmt = (
        select(
            Conversation,
            User,
            func.coalesce(counts_sq.c.messages_count, 0).label("messages_count"),
        )
        .join(User, User.id == Conversation.user_id)
        .outerjoin(
            counts_sq, counts_sq.c.conversation_id == Conversation.id
        )
    )
    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Conversation.title).like(like)
            | func.lower(User.email).like(like)
            | func.lower(User.name).like(like)
        )
    stmt = (
        stmt.order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    out: list[dict[str, Any]] = []
    for conv, owner, count in rows:
        out.append(
            {
                "id": conv.id,
                "user_id": conv.user_id,
                "user_email": owner.email,
                "user_name": owner.name,
                "title": conv.title,
                "model": conv.model,
                "status": conv.status,
                "messages_count": int(count or 0),
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
            }
        )
    return out


async def get_conversation_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    limit: int = 200,
    offset: int = 0,
) -> list[Message]:
    """Todos los mensajes de una conversación, en orden cronológico."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.scalars(stmt)).all())


async def get_user_stats(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Métricas agregadas de un usuario."""
    await get_user(session, user_id)  # valida existencia

    conversations_total = int(
        await session.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
        or 0
    )

    msg_row = (
        await session.execute(
            select(
                func.count(Message.id),
                func.coalesce(func.sum(Message.tokens_in), 0),
                func.coalesce(func.sum(Message.tokens_out), 0),
                func.max(Message.created_at),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user_id)
        )
    ).one()
    messages_total = int(msg_row[0] or 0)
    tok_in = int(msg_row[1] or 0)
    tok_out = int(msg_row[2] or 0)
    last_activity = msg_row[3]

    cost = (
        (tok_in / 1_000_000) * _PRICE_INPUT_PER_M_A2
        + (tok_out / 1_000_000) * _PRICE_OUTPUT_PER_M_A2
    )

    memories_active = int(
        await session.scalar(
            select(func.count())
            .select_from(Memory)
            .where(Memory.user_id == user_id, Memory.status == "ACTIVE")
        )
        or 0
    )

    documents_active = int(
        await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.owner_user_id == user_id,
                Document.deleted_at.is_(None),
                Document.hidden_at.is_(None),
            )
        )
        or 0
    )

    return {
        "conversations_total": conversations_total,
        "messages_total": messages_total,
        "tokens_in_total": tok_in,
        "tokens_out_total": tok_out,
        "cost_estimate_usd": round(cost, 4),
        "memories_active": memories_active,
        "documents_active": documents_active,
        "last_activity_at": last_activity,
    }


async def get_user_detail(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Vista agregada: perfil + stats + últimas conversaciones/memorias/docs."""
    user = await get_user(session, user_id)
    stats = await get_user_stats(session, user_id=user_id)
    recent_conversations = await list_user_conversations(
        session, user_id=user_id, limit=5, offset=0
    )
    recent_memories = list(
        (
            await session.scalars(
                select(Memory)
                .where(Memory.user_id == user_id, Memory.status == "ACTIVE")
                .order_by(Memory.created_at.desc())
                .limit(5)
            )
        ).all()
    )
    recent_documents = list(
        (
            await session.scalars(
                select(Document)
                .where(Document.owner_user_id == user_id)
                .order_by(Document.created_at.desc())
                .limit(5)
            )
        ).all()
    )
    return {
        "user": user,
        "stats": stats,
        "recent_conversations": recent_conversations,
        "recent_memories": recent_memories,
        "recent_documents": recent_documents,
    }