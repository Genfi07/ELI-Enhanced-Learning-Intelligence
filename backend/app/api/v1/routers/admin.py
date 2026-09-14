"""Endpoints de administración.

Todos requieren permisos específicos (RBAC). No basta con estar autenticado.
Los permisos usados:
  - users.read / users.write / users.delete
  - admin.panel / admin.config / admin.audit
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.schemas import (
    AdminUserOut,
    AnalyticsOverview,
    AuditLogOut,
    BlockUserIn,
    ChangeRoleIn,
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
from app.tools.registry import build_registry
from app.llm.embeddings_router import build_embeddings_provider

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


@router.get("/config/{key}", response_model=SettingOut)
async def get_config(
    key: str,
    _: User = Depends(require_permission("admin.config")),
) -> SettingOut:
    items = await dynamic.list_all_settings_with_metadata()
    for item in items:
        if item["key"] == key:
            return SettingOut(**item)
    from fastapi import HTTPException
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
    from fastapi import HTTPException
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
    # Ping ligero a la BD
    db_status = "ok"
    try:
        await session.execute(__import__("sqlalchemy").text("SELECT 1"))
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