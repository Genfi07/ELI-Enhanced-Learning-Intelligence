from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk


class SystemSetting(Base, UUIDPk):
    """Configuración del sistema en BD.

    Cada fila representa una clave del settings dinámico. Los defaults siguen
    viviendo en `app.config.settings.Settings`; esta tabla contiene SOLO los
    overrides que un admin ha guardado.

    Si una clave existe aquí, gana sobre el default. Si no existe, se usa el
    default del código.

    Values siempre JSONB para soportar strings, números, booleanos y listas.
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    category: Mapped[str] = mapped_column(
        String(40), default="general", nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Auditoría: quién modificó por última vez y cuándo.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_system_settings_category", "category"),
    )


class AuditLog(Base, UUIDPk):
    """Registro de acciones administrativas y cambios sensibles.

    Cada acción tiene:
      - actor: quién (user_id, o NULL si es sistema)
      - action: qué (ej: "user.block", "config.update", "tool.disable")
      - entity_type/entity_id: sobre qué entidad
      - before/after: estado antes y después (JSONB)
      - metadata: IP, user-agent, request_id, razón

    Solo se registra lo que merece auditoría: acciones de admin, cambios de
    configuración, bloqueos, cambios de rol. NO se registra cada request
    normal (eso vive en request_traces).
    """

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Metadata: ip, user_agent, request_id, reason, etc.
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
    )