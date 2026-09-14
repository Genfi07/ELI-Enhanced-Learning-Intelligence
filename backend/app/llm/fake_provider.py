from collections.abc import AsyncIterator

from app.core.schemas.llm import LLMChunk, LLMMessage, LLMResponse, TokenUsage
from app.llm.base import count_messages_tokens, rough_token_count


class FakeLLMProvider:
    """Proveedor determinista para tests y desarrollo sin API key.

    Reglas:
      - Si el último mensaje de usuario contiene 'ECHO:', devuelve el resto tal cual.
      - Si contiene 'SLOW:', hace streaming token a token (para test de SSE).
      - En cualquier otro caso responde con un texto fijo.
    """

    name = "fake"

    def __init__(self, model: str = "fake-1") -> None:
        self.model = model

    def _response_text(self, messages: list[LLMMessage]) -> str:
        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        text = last_user.content if last_user else ""
        if "ECHO:" in text:
            return text.split("ECHO:", 1)[1].strip()
        return f"[ELI-fake] He recibido tu mensaje: {text[:200]}"

    async def generate(
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ) -> LLMResponse:
        text = self._response_text(messages)
        usage = TokenUsage(
            prompt_tokens=count_messages_tokens(messages),
            completion_tokens=rough_token_count(text),
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        return LLMResponse(text=text, usage=usage, model=model or self.model)

    async def stream(  # type: ignore[override]
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ) -> AsyncIterator[LLMChunk]:
        text = self._response_text(messages)
        for token in text.split(" "):
            yield LLMChunk(delta=token + " ")
        usage = TokenUsage(
            prompt_tokens=count_messages_tokens(messages),
            completion_tokens=rough_token_count(text),
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        yield LLMChunk(is_final=True, usage=usage)

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        return count_messages_tokens(messages)