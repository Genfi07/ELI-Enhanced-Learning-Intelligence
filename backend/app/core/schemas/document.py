from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DocumentStatus = Literal["PENDING", "PROCESSING", "READY", "FAILED"]
DocumentScope = Literal["USER", "ORG", "GLOBAL"]

# Estado derivado para la UI (Activo / Eliminado / Oculto).
DocumentVisibility = Literal["ACTIVE", "DELETED", "HIDDEN"]


class DocumentOut(BaseModel):
    """Vista pública de un documento."""
    id: uuid.UUID
    title: str
    mime_type: str
    size_bytes: int
    status: str
    scope: str
    chunk_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime

    # Ciclo de vida efímero
    deleted_at: datetime | None = None
    hidden_at: datetime | None = None
    physical_deleted_at: datetime | None = None

    # Contenido "recordado" por ELI (sobrevive al borrado de chunks)
    summary: str | None = None
    topics: list[str] = Field(default_factory=list)

    @classmethod
    def from_model(cls, d) -> "DocumentOut":
        return cls(
            id=d.id,
            title=d.title,
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            status=d.status,
            scope=d.scope,
            chunk_count=d.chunk_count,
            error=d.error,
            created_at=d.created_at,
            updated_at=d.updated_at,
            deleted_at=d.deleted_at,
            hidden_at=d.hidden_at,
            physical_deleted_at=d.physical_deleted_at,
            summary=d.summary,
            topics=list(d.topics or []),
        )


class RetrievedChunk(BaseModel):
    """Un fragmento recuperado con su score y datos de origen."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    score: float
    similarity: float
    meta: dict = Field(default_factory=dict)