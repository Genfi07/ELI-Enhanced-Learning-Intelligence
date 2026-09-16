from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
class AdminUserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    status: str
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_model(cls, u) -> "AdminUserOut":
        return cls(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role.name if u.role else "USER",
            status=u.status,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )


class ChangeRoleIn(BaseModel):
    role: str = Field(pattern="^(USER|MODERATOR|ADMIN|SUPER_ADMIN)$")


class BlockUserIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class SettingOut(BaseModel):
    key: str
    value: Any
    default: Any
    is_override: bool
    category: str
    description: str | None
    updated_at: datetime | None
    updated_by: uuid.UUID | None


class SettingUpdateIn(BaseModel):
    value: Any
    category: str | None = None
    description: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: str | None
    before: dict | None
    after: dict | None
    meta: dict
    created_at: datetime

    @classmethod
    def from_model(cls, a) -> "AuditLogOut":
        return cls(
            id=a.id,
            actor_user_id=a.actor_user_id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            before=a.before,
            after=a.after,
            meta=a.meta or {},
            created_at=a.created_at,
        )


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
class AnalyticsOverview(BaseModel):
    users_total: int
    users_active: int
    users_blocked: int
    conversations_total: int
    messages_total: int
    memories_total: int
    documents_total: int
    tool_calls_total: int
    tokens_total: int
    cost_estimate_usd: float
    errors_total: int


class TimeseriesPoint(BaseModel):
    date: str
    messages: int
    tokens: int
    errors: int


class TimeseriesOut(BaseModel):
    days: int
    points: list[TimeseriesPoint]


# --------------------------------------------------------------------------- #
# System
# --------------------------------------------------------------------------- #
class SystemHealth(BaseModel):
    status: str
    database: str
    llm_provider: str
    embeddings_provider: str
    tools_count: int
    env: str
    version: str

    

# --------------------------------------------------------------------------- #
# Create & Promote users
# --------------------------------------------------------------------------- #
class CreateUserIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(
        default="USER",
        pattern="^(USER|MODERATOR|ADMIN|SUPER_ADMIN)$",
    )


class PromoteToSuperIn(BaseModel):
    """Requiere confirm: true para evitar promociones accidentales."""

    confirm: bool = Field(
        description="Debe ser true. Evita accidentes por click erróneo."
    )
class ResetAllSettingsOut(BaseModel):
    """Resultado de restablecer toda la configuración."""

    deleted: int = Field(description="Número de overrides eliminados")

    # --------------------------------------------------------------------------- #
# Config guide
# --------------------------------------------------------------------------- #
class GuideEntry(BaseModel):
    key: str
    category: str
    short: str
    description: str
    values: str | None = None
    impact: str | None = None
    example: str | None = None

    # --------------------------------------------------------------------------- #
# A2 — Conversaciones, mensajes y stats por usuario
# --------------------------------------------------------------------------- #
class AdminConversationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    user_name: str | None = None
    title: str
    model: str | None = None
    status: str
    messages_count: int
    created_at: datetime
    updated_at: datetime


class AdminMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tokens_in: int
    tokens_out: int
    model: str | None = None
    created_at: datetime


class AdminUserStatsOut(BaseModel):
    conversations_total: int
    messages_total: int
    tokens_in_total: int
    tokens_out_total: int
    cost_estimate_usd: float
    memories_active: int
    documents_active: int
    last_activity_at: datetime | None = None


class AdminMemoryOut(BaseModel):
    id: uuid.UUID
    type: str
    content: str
    importance: float
    confidence: float
    status: str
    created_at: datetime
    last_used_at: datetime | None = None


class AdminDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    mime_type: str
    size_bytes: int
    status: str
    chunk_count: int
    created_at: datetime
    deleted_at: datetime | None = None
    hidden_at: datetime | None = None


class AdminUserDetailOut(BaseModel):
    user: AdminUserOut
    stats: AdminUserStatsOut
    recent_conversations: list[AdminConversationOut]
    recent_memories: list[AdminMemoryOut]
    recent_documents: list[AdminDocumentOut]