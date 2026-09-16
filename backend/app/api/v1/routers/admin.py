"""Endpoints de administración.

Todos requieren permisos específicos (RBAC). No basta con estar autenticado.
Los permisos usados:
  - users.read / users.write / users.delete
  - admin.panel / admin.config / admin.audit
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.schemas import (
    AdminConversationOut,
    AdminDocumentOut,
    AdminMemoryOut,
    AdminMessageOut,
    AdminUserDetailOut,
    AdminUserOut,
    AdminUserStatsOut,
    AnalyticsOverview,
    AuditLogOut,
    BlockUserIn,
    ChangeRoleIn,
    CreateUserIn,
    GuideEntry,
    PromoteToSuperIn,
    ResetAllSettingsOut,
    SettingOut,
    SettingUpdateIn,
    SystemHealth,
    TimeseriesOut,
)
from app.api.deps import current_user, db_session
from app.auth.rbac import require_permission
from app.config import dynamic
from app.config.settings import get_settings
from app.db.models.user import User
from app.llm.embeddings_router import build_embeddings_provider
from app.tools.registry import build_registry

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    status_filter: str | None = Query(default=None, alias="status"),
    role: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(db_session),
) -> list[AdminUserOut]:
    users = await service.list_users(
        session,
        status=status_filter,
        role=role,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [AdminUserOut.from_model(u) for u in users]


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: uuid.UUID,
    _: User = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserOut:
    u = await service.get_user(session, user_id)
    return AdminUserOut.from_model(u)


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def admin_create_user(
    body: CreateUserIn,
    request: Request,
    actor: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserOut:
    user = await service.create_user(
        session,
        actor=actor,
        name=body.name,
        email=body.email,
        password=body.password,
        role_name=body.role,
        request=request,
    )
    await session.commit()
    await session.refresh(user, ["role"])
    return AdminUserOut.from_model(user)


@router.post("/users/{user_id}/promote", response_model=AdminUserOut)
async def admin_promote_user(
    user_id: uuid.UUID,
    body: PromoteToSuperIn,
    request: Request,
    actor: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserOut:
    if not body.confirm:
        raise HTTPException(
            status_code=400, detail="Debes confirmar la promoción"
        )
    user = await service.promote_to_super_admin(
        session,
        actor=actor,
        target_id=user_id,
        request=request,
    )
    await session.commit()
    await session.refresh(user, ["role"])
    return AdminUserOut.from_model(user)


@router.patch("/users/{user_id}/role", response_model=AdminUserOut)
async def change_user_role(
    user_id: uuid.UUID,
    body: ChangeRoleIn,
    request: Request,
    actor: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserOut:
    target = await service.change_user_role(
        session,
        actor=actor,
        target_id=user_id,
        new_role_name=body.role,
        request=request,
    )
    await session.commit()
    return AdminUserOut.from_model(target)


@router.post("/users/{user_id}/block", response_model=AdminUserOut)
async def block_user(
    user_id: uuid.UUID,
    body: BlockUserIn,
    request: Request,
    actor: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserOut:
    target = await service.block_user(
        session,
        actor=actor,
        target_id=user_id,
        reason=body.reason,
        request=request,
    )
    await session.commit()
    return AdminUserOut.from_model(target)


@router.post("/users/{user_id}/unblock", response_model=AdminUserOut)
async def unblock_user(
    user_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserOut:
    target = await service.unblock_user(
        session, actor=actor, target_id=user_id, request=request
    )
    await session.commit()
    return AdminUserOut.from_model(target)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require_permission("users.delete")),
    session: AsyncSession = Depends(db_session),
) -> None:
    await service.soft_delete_user(
        session, actor=actor, target_id=user_id, request=request
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@router.get("/config", response_model=list[SettingOut])
async def list_config(
    _: User = Depends(require_permission("admin.config")),
) -> list[SettingOut]:
    items = await dynamic.list_all_settings_with_metadata()
    return [SettingOut(**item) for item in items]


# IMPORTANTE: /config/guide debe ir ANTES de /config/{key}
# porque FastAPI resuelve rutas en orden de declaración.
@router.get("/config/guide", response_model=list[GuideEntry])
async def admin_config_guide(
    _: User = Depends(require_permission("admin.config")),
    session: AsyncSession = Depends(db_session),
) -> list[GuideEntry]:
    """Guía descriptiva de cada clave de configuración."""
    entries = await service.get_config_guide(session)
    return [GuideEntry(**e) for e in entries]


@router.get("/config/{key}", response_model=SettingOut)
async def get_config(
    key: str,
    _: User = Depends(require_permission("admin.config")),
) -> SettingOut:
    items = await dynamic.list_all_settings_with_metadata()
    for item in items:
        if item["key"] == key:
            return SettingOut(**item)
    raise HTTPException(status_code=404, detail="Clave no encontrada")


@router.put("/config/{key}", response_model=SettingOut)
async def update_config(
    key: str,
    body: SettingUpdateIn,
    request: Request,
    actor: User = Depends(require_permission("admin.config")),
    session: AsyncSession = Depends(db_session),
) -> SettingOut:
    await service.set_setting(
        session,
        actor=actor,
        key=key,
        value=body.value,
        category=body.category,
        description=body.description,
        request=request,
    )
    await session.commit()
    items = await dynamic.list_all_settings_with_metadata()
    for item in items:
        if item["key"] == key:
            return SettingOut(**item)
    raise HTTPException(status_code=500, detail="Config no persistida")


@router.delete("/config/{key}", status_code=204)
async def delete_config(
    key: str,
    request: Request,
    actor: User = Depends(require_permission("admin.config")),
    session: AsyncSession = Depends(db_session),
) -> None:
    await service.delete_setting(session, actor=actor, key=key, request=request)
    await session.commit()


@router.post("/settings/reset-all", response_model=ResetAllSettingsOut)
async def admin_reset_all_settings(
    request: Request,
    actor: User = Depends(require_permission("admin.config")),
    session: AsyncSession = Depends(db_session),
) -> ResetAllSettingsOut:
    """Borra todos los overrides y vuelve a los valores por defecto."""
    deleted = await service.reset_all_settings(
        session, actor=actor, request=request
    )
    await session.commit()
    return ResetAllSettingsOut(deleted=deleted)


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
@router.get("/audit", response_model=list[AuditLogOut])
async def list_audit(
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission("admin.audit")),
    session: AsyncSession = Depends(db_session),
) -> list[AuditLogOut]:
    rows = await service.list_audit_logs(
        session,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )
    return [AuditLogOut.from_model(r) for r in rows]


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
@router.get("/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> AnalyticsOverview:
    data = await service.get_analytics_overview(session)
    return AnalyticsOverview(**data)


@router.get("/analytics/timeseries", response_model=TimeseriesOut)
async def analytics_timeseries(
    days: int = Query(default=7, ge=1, le=90),
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> TimeseriesOut:
    points = await service.get_timeseries(session, days=days)
    return TimeseriesOut(days=days, points=points)


# --------------------------------------------------------------------------- #
# System
# --------------------------------------------------------------------------- #
@router.get("/system/health", response_model=SystemHealth)
async def system_health(
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> SystemHealth:
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    settings = get_settings()
    reg = build_registry()
    emb = build_embeddings_provider()

    return SystemHealth(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        llm_provider=settings.llm_provider,
        embeddings_provider=emb.name,
        tools_count=len(reg.names()),
        env=settings.env,
        version="0.1.0",
    )


# --------------------------------------------------------------------------- #
# A2 — Conversaciones, mensajes y stats por usuario
#
# Nota de seguridad: los endpoints que exponen CONTENIDO de conversaciones
# requieren admin.panel (solo SUPER_ADMIN). Solo /stats queda en users.read,
# porque no revela contenido, solo agregados numéricos.
# --------------------------------------------------------------------------- #
@router.get(
    "/users/{user_id}/conversations",
    response_model=list[AdminConversationOut],
)
async def admin_user_conversations(
    user_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> list[AdminConversationOut]:
    rows = await service.list_user_conversations(
        session, user_id=user_id, limit=limit, offset=offset
    )
    return [AdminConversationOut(**r) for r in rows]


@router.get("/users/{user_id}/stats", response_model=AdminUserStatsOut)
async def admin_user_stats(
    user_id: uuid.UUID,
    _: User = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserStatsOut:
    """Stats agregados: no expone contenido de conversaciones."""
    data = await service.get_user_stats(session, user_id=user_id)
    return AdminUserStatsOut(**data)


@router.get("/users/{user_id}/detail", response_model=AdminUserDetailOut)
async def admin_user_detail(
    user_id: uuid.UUID,
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> AdminUserDetailOut:
    data = await service.get_user_detail(session, user_id=user_id)
    return AdminUserDetailOut(
        user=AdminUserOut.from_model(data["user"]),
        stats=AdminUserStatsOut(**data["stats"]),
        recent_conversations=[
            AdminConversationOut(**c) for c in data["recent_conversations"]
        ],
        recent_memories=[
            AdminMemoryOut(
                id=m.id,
                type=m.type,
                content=m.content,
                importance=m.importance,
                confidence=m.confidence,
                status=m.status,
                created_at=m.created_at,
                last_used_at=m.last_used_at,
            )
            for m in data["recent_memories"]
        ],
        recent_documents=[
            AdminDocumentOut(
                id=d.id,
                title=d.title,
                mime_type=d.mime_type,
                size_bytes=d.size_bytes,
                status=d.status,
                chunk_count=d.chunk_count,
                created_at=d.created_at,
                deleted_at=d.deleted_at,
                hidden_at=d.hidden_at,
            )
            for d in data["recent_documents"]
        ],
    )


@router.get("/conversations", response_model=list[AdminConversationOut])
async def admin_list_conversations(
    user_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> list[AdminConversationOut]:
    rows = await service.list_all_conversations(
        session,
        user_id=user_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [AdminConversationOut(**r) for r in rows]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[AdminMessageOut],
)
async def admin_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission("admin.panel")),
    session: AsyncSession = Depends(db_session),
) -> list[AdminMessageOut]:
    msgs = await service.get_conversation_messages(
        session, conversation_id=conversation_id, limit=limit, offset=offset
    )
    return [
        AdminMessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            tokens_in=m.tokens_in,
            tokens_out=m.tokens_out,
            model=m.model,
            created_at=m.created_at,
        )
        for m in msgs
    ]