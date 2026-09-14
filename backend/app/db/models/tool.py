from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk


class Tool(Base, UUIDPk, Timestamps):
    """Declaración persistida de una herramienta disponible en ELI.

    Estados:
      - enabled=True  → puede invocarse (sujeto a permisos y autonomía)
      - enabled=False → denegada con 403 aunque se pida explícitamente

    Scopes (para futuro multi-tenant):
      - builtin: viene con ELI, solo SUPER_ADMIN puede desactivarla
      - user:    instalada por un usuario (Fase 7+)
      - org:     instalada por una organización (Fase 7+)
    """

    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="builtin", nullable=False)

    # JSON Schema de los parámetros que acepta la tool.
    parameters_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    # Lista de códigos de permiso requeridos (ej: ["tools.web"]).
    required_permissions: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )

    # Nivel mínimo de autonomía del usuario para poder invocarla (0-4).
    min_autonomy_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Si True, las llamadas quedan pendientes de confirmación del usuario.
    # Típicamente True para nivel 4. Puede ser True también para cualquier
    # tool que un admin marque como "peligrosa".
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Timeout duro en milisegundos. El runtime lo aplica con asyncio.wait_for.
    timeout_ms: Mapped[int] = mapped_column(Integer, default=10_000, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Metadata libre: categoría, autor, versión, etc.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", name="uq_tools_name"),
        Index("ix_tools_enabled_scope", "enabled", "scope"),
    )


class ToolCall(Base, UUIDPk):
    """Registro de una invocación de herramienta. Auditoría completa."""

    __tablename__ = "tool_calls"

    # Contexto de la llamada. conversation_id puede ser NULL si viene de un
    # test directo o de un cron. user_id es obligatorio para aislamiento.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    tool_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    # Argumentos y resultado como JSONB (pueden ser estructurados).
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    result: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    # OK | ERROR | TIMEOUT | DENIED | PENDING_CONFIRMATION
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Con qué nivel de autonomía se autorizó (0-4).
    autonomy_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )

    __table_args__ = (
        Index("ix_tool_calls_user_created", "user_id", "created_at"),
        Index("ix_tool_calls_tool_status", "tool_name", "status"),
    )


class PendingAction(Base, UUIDPk, Timestamps):
    """Acción sensible esperando confirmación explícita del usuario.

    Cuando el runtime autoriza una tool con `requires_confirmation=True`,
    NO ejecuta: crea un PendingAction y devuelve su id. El usuario confirma
    después con POST /tools/pending-actions/{id}/confirm y ahí se ejecuta.
    """

    __tablename__ = "pending_actions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    # PENDING | CONFIRMED | REJECTED | EXPIRED
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )

    # Explicación para el usuario (por qué se requiere confirmación).
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Cuando se ejecuta, guardamos el resultado aquí para consulta posterior.
    result: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_pending_actions_user_status", "user_id", "status"),
    )