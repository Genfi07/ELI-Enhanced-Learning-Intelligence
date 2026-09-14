from typing import Literal
from pydantic import BaseModel


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class LLMResponse(BaseModel):
    text: str | None
    tool_calls: list[ToolCall] = []
    usage: TokenUsage
    finish_reason: str = "stop"
    model: str


class LLMChunk(BaseModel):
    """Fragmento de streaming. `is_final=True` cierra y trae usage/ids."""
    delta: str = ""
    is_final: bool = False
    usage: TokenUsage | None = None