from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from app.db.base import Base, UUIDPk

# Dimensión del vector de embeddings. Fijada al valor de
# text-embedding-3-small de OpenAI. Cambiar aquí implicaría migración.
EMBEDDING_DIM = 1536


class Memory(Base, UUIDPk):
    """Un recuerdo persistente de ELI sobre un usuario.

    Tipos:
      - FACT:       información objetiva ("trabaja en finanzas")
      - PREFERENCE: cómo quiere que le respondan ("prefiere paso a paso")
      - GOAL:       objetivo en curso ("está aprendiendo Rust")
      - INSTRUCTION: regla explícita ("siempre responde en inglés")
      - EPISODE:    resumen de una conversación relevante

    Estados:
      - ACTIVE:     vigente, se puede recuperar
      - SUPERSEDED: reemplazado por otro recuerdo (se conserva el historial)
      - DELETED:    borrado por el usuario (soft-delete, invisible)
    """

    __tablename__ = "memories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Scoring y control
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="INFERRED", nullable=False)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Vector de embedding (pgvector). Nullable al crear, se rellena en el mismo turno.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    # Estado
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Uso
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Auditoría
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    # Metadata libre (para evolucionar sin migrar)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    __table_args__ = (
        Index("ix_memories_user_status_type", "user_id", "status", "type"),
        Index("ix_memories_user_last_used", "user_id", "last_used_at"),
    )


class MemoryEvent(Base, UUIDPk):
    """Auditoría de cambios en memoria.

    Permite responder "¿qué cambió y por qué?" y reconstruir el historial.
    Nunca se borra automáticamente.
    """

    __tablename__ = "memory_events"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    # CREATED | UPDATED | MERGED | SUPERSEDED | DELETED | RESTORED

    previous_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(20), default="ELI", nullable=False)
    # ELI | USER | SYSTEM

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )