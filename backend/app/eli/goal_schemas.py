"""Esquemas Pydantic para el router de metas de ELI."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


GoalKind = Literal["LEARN", "EXPLORE", "IMPROVE", "CONNECT", "PROPOSE"]
GoalOrigin = Literal["SELF", "TAUGHT", "DETECTED"]
GoalStatus = Literal["ACTIVE", "PAUSED", "ACHIEVED", "ABANDONED"]


class GoalOut(BaseModel):
    id: uuid.UUID
    kind: GoalKind
    content: str
    origin: GoalOrigin
    priority: int
    status: GoalStatus
    progress_notes: list[dict[str, Any]]
    source_conversation_id: uuid.UUID | None
    detected_pattern: str | None
    related_topics: list[str]
    created_at: datetime
    updated_at: datetime
    achieved_at: datetime | None
    abandoned_at: datetime | None

    @classmethod
    def from_model(cls, m: Any) -> "GoalOut":
        return cls(
            id=m.id,
            kind=m.kind,
            content=m.content,
            origin=m.origin,
            priority=m.priority,
            status=m.status,
            progress_notes=list(m.progress_notes or []),
            source_conversation_id=m.source_conversation_id,
            detected_pattern=m.detected_pattern,
            related_topics=list(m.related_topics or []),
            created_at=m.created_at,
            updated_at=m.updated_at,
            achieved_at=m.achieved_at,
            abandoned_at=m.abandoned_at,
        )


class GoalCreateIn(BaseModel):
    kind: GoalKind
    content: str = Field(min_length=5, max_length=800)
    priority: int = Field(default=3, ge=1, le=5)
    related_topics: list[str] = Field(default_factory=list)


class GoalUpdateIn(BaseModel):
    status: GoalStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    content: str | None = Field(default=None, min_length=5, max_length=800)


class GoalNoteIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)