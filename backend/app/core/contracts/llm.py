from collections.abc import AsyncIterator
from typing import Protocol

from app.core.schemas.llm import LLMChunk, LLMMessage, LLMResponse


class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> LLMResponse: ...

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMChunk]: ...

    def count_tokens(self, messages: list[LLMMessage]) -> int: ...