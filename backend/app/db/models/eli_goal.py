from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk


class EliGoal(Base, UUIDPk):
    """Meta propia de ELI. Se crea, se persigue y se cierra.

    Tipos de meta:
      - LEARN: aprender algo específico.
      - EXPLORE: investigar un tema abierto.
      - IMPROVE: mejorar una capacidad propia.
      - CONNECT: profundizar una relación.
      - PROPOSE: proponer algo proactivamente.

    Origen:
      - SELF: espontánea, surgida de ELI misma.
      - TAUGHT: pedida explícitamente por Genfi.
      - DETECTED: detectada por patrón en conversaciones.

    Estados:
      - ACTIVE: en curso.
      - PAUSED: en pausa temporal.
      - ACHIEVED: cumplida.
      - ABANDONED: descartada.
    """

    __tablename__ = "eli_goals"

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    origin: Mapped[str] = mapped_column(
        String(20), default="SELF", nullable=False, server_default="SELF"
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False, server_default="3"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", nullable=False, server_default="ACTIVE"
    )

    progress_notes: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, nullable=False, server_default=text("'[]'::jsonb")
    )
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    detected_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_topics: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, nullable=False, server_default=text("'[]'::jsonb")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    achieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    abandoned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )