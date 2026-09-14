import uuid
from typing import Any

from pydantic import BaseModel

from app.core.schemas.plan import ProcessingPlan


class TurnRequest(BaseModel):
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    message: str


class TurnResult(BaseModel):
    request_id: str
    conversation_id: uuid.UUID
    assistant_message_id: uuid.UUID
    text: str
    route: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class TurnTrace(BaseModel):
    request_id: str
    user_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    route: str
    plan: dict[str, Any]
    steps: list[dict[str, Any]]
    total_latency_ms: int
    status: str
    error: str | None = None