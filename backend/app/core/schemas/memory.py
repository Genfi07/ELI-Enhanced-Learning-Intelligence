from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MemoryType = Literal["FACT", "PREFERENCE", "GOAL", "INSTRUCTION", "EPISODE"]
MemorySource = Literal["EXPLICIT", "INFERRED", "DOCUMENT"]
MemoryStatus = Literal["ACTIVE", "SUPERSEDED", "DELETED"]


class MemoryCandidate(BaseModel):
    """Propuesta de memoria antes de persistirla.

    El MemoryExtractor produce estos objetos; el MemoryStore los valida y guarda.
    """
    type: MemoryType
    content: str = Field(min_length=3, max_length=2000)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source: MemorySource = "INFERRED"


class MemoryOut(BaseModel):
    """Vista pública de una memoria (endpoint /memory)."""
    id: uuid.UUID
    type: str
    content: str
    importance: float
    confidence: float
    source: str
    status: str
    usage_count: int
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None

    @classmethod
    def from_model(cls, m) -> "MemoryOut":
        return cls(
            id=m.id,
            type=m.type,
            content=m.content,
            importance=m.importance,
            confidence=m.confidence,
            source=m.source,
            status=m.status,
            usage_count=m.usage_count,
            created_at=m.created_at,
            updated_at=m.updated_at,
            last_used_at=m.last_used_at,
        )


class MemorySearchResult(BaseModel):
    """Resultado de búsqueda con score combinado."""
    memory_id: uuid.UUID
    content: str
    type: str
    score: float


class MemoryEventOut(BaseModel):
    id: uuid.UUID
    memory_id: uuid.UUID
    event: str
    previous_content: str | None
    reason: str | None
    actor: str
    created_at: datetime