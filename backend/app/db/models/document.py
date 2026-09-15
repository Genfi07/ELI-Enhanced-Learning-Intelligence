from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from app.db.base import Base, Timestamps, UUIDPk

EMBEDDING_DIM = 1536


class Document(Base, UUIDPk, Timestamps):
    """Un documento subido por el usuario.

    Ciclo de vida efímero:
      1. Subida → PENDING. El archivo físico vive en storage.
      2. Ingesta → PROCESSING → READY. El archivo físico se BORRA.
         A partir de aquí, solo existen chunks + embeddings en BD.
      3. Usuario elimina → deleted_at se setea. Los chunks se borran.
         La entrada queda visible como "Eliminado" (tachado en rojo).
      4. Usuario oculta → hidden_at se setea. La entrada desaparece de UI.
         ELI sigue sabiendo que existió (por el resumen + topics).

    Estados (`status`):
      - PENDING, PROCESSING, READY, FAILED

    Visibilidad (derivada, no es un campo):
      - Activo: deleted_at IS NULL AND hidden_at IS NULL
      - Eliminado: deleted_at IS NOT NULL AND hidden_at IS NULL
      - Oculto: hidden_at IS NOT NULL
    """

    __tablename__ = "documents"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    scope: Mapped[str] = mapped_column(String(20), default="USER", nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), default="UPLOAD", nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- Ciclo de vida efímero ----
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    physical_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ---- Resumen + topics para que ELI recuerde el documento ----
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Metadata libre adicional (páginas, autor, idioma, etc.).
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_documents_owner_status", "owner_user_id", "status"),
        Index("ix_documents_owner_scope", "owner_user_id", "scope"),
        Index("ix_documents_owner_deleted", "owner_user_id", "deleted_at"),
        Index("ix_documents_owner_hidden", "owner_user_id", "hidden_at"),
    )


class DocumentChunk(Base, UUIDPk):
    """Un fragmento de un documento, con embedding para búsqueda semántica."""

    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_document_chunks_doc_index", "document_id", "chunk_index"),
    )