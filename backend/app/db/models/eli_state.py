from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk


class EliState(Base, UUIDPk):
    """Estado interno actual de ELI (singleton, una sola fila)."""

    __tablename__ = "eli_state"

    # Estado afectivo actual
    mood: Mapped[str] = mapped_column(String(20), nullable=False, default="tranquila")
    energy: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    focus: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    curiosity: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)

    # Timestamps de referencia
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_initiated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Contador de turnos desde la última actualización
    turns_since_update: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Listas dinámicas
    pending_thoughts: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    recent_topics: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )


class EliStateHistory(Base, UUIDPk):
    """Historial de cambios del estado interno de ELI."""

    __tablename__ = "eli_state_history"

    mood: Mapped[str] = mapped_column(String(20), nullable=False)
    energy: Mapped[float] = mapped_column(Float, nullable=False)
    focus: Mapped[float] = mapped_column(Float, nullable=False)
    curiosity: Mapped[float] = mapped_column(Float, nullable=False)

    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )