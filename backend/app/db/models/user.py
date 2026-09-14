from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk


class User(Base, UUIDPk, Timestamps):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped["Role"] = relationship("Role", lazy="joined")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Preferencias del usuario. Claves típicas:
    #   autonomy_level: int (0-4)  → qué nivel de acciones puede autorizar ELI
    #   response_style: str        → "concise" | "detailed" | ...
    #   language: str              → "es" | "en" | ...
    #
    # OJO: server_default debe ir como text(...), NO como string literal.
    # Si se pasa como string, SQLAlchemy lo envuelve en comillas adicionales
    # y genera SQL inválido (`DEFAULT '''{}''::jsonb'`).
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )