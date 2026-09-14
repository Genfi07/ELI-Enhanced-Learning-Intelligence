from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from app.db.base import Base, Timestamps, UUIDPk

# Misma dimensión que memories para reutilizar EmbeddingsProvider.
EMBEDDING_DIM = 1536


class Document(Base, UUIDPk, Timestamps):
    """Un documento subido por el usuario.

    Estados:
      - PENDING: recién subido, esperando procesamiento
      - PROCESSING: extrayendo texto / generando embeddings
      - READY: procesado y disponible para búsqueda
      - FAILED: falló el procesamiento (ver `error`)

    Scopes (para futuro multi-tenant):
      - USER: visible solo para el dueño
      - ORG: visible para todos los miembros de la organización
      - GLOBAL: visible para todos (solo admins pueden crear)
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

    # Número total de chunks generados. Útil para UI y para detectar reprocesamiento.
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Metadata libre: número de páginas, autor, idioma detectado, etc.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_documents_owner_status", "owner_user_id", "status"),
        Index("ix_documents_owner_scope", "owner_user_id", "scope"),
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

    # Vector de embedding. Nullable para permitir inserciones en batch.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    # Metadata por chunk: página de origen, sección, etc.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_document_chunks_doc_index", "document_id", "chunk_index"),
    )