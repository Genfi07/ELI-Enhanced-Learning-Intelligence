from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings
from app.core.schemas.llm import LLMChunk, LLMMessage, LLMResponse, TokenUsage
from app.llm.base import count_messages_tokens


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        key = api_key or settings.openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY no configurada")
        client_kwargs: dict = {
            "api_key": key,
            "timeout": settings.llm_request_timeout_s,
        }
        if settings.openai_base_url:
            # DeepSeek, Ollama y otros endpoints OpenAI-compatible.
            client_kwargs["base_url"] = settings.openai_base_url
        self._client = AsyncOpenAI(**client_kwargs)
        self._default_model = settings.llm_default_model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.4, max=2.0))
    async def generate(self, messages, *, model=None, temperature=0.7, max_tokens=None) -> LLMResponse:
        resp = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=[m.model_dump() for m in messages],
            temperature=temperature,
            max_tokens=max_tokens or get_settings().max_response_tokens,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            text=choice.message.content or "",
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason=choice.finish_reason or "stop",
            model=resp.model,
        )

    async def stream(  # type: ignore[override]
        self, messages, *, model=None, temperature=0.7, max_tokens=None
    ) -> AsyncIterator[LLMChunk]:
        stream = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=[m.model_dump() for m in messages],
            temperature=temperature,
            max_tokens=max_tokens or get_settings().max_response_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for event in stream:
            if event.choices:
                delta = event.choices[0].delta.content or ""
                if delta:
                    yield LLMChunk(delta=delta)
            if event.usage is not None:
                yield LLMChunk(
                    is_final=True,
                    usage=TokenUsage(
                        prompt_tokens=event.usage.prompt_tokens,
                        completion_tokens=event.usage.completion_tokens,
                        total_tokens=event.usage.total_tokens,
                    ),
                )

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        # Aproximación conservadora; sustituible por tiktoken en Fase 5.
        return count_messages_tokens(messages)