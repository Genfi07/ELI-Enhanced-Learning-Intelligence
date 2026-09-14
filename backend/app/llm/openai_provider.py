"""OpenAIProvider: cliente HTTP contra cualquier endpoint OpenAI-compatible.

Acepta `name`, `api_key`, `base_url` y `default_model` como parámetros
opcionales. Si no se pasan, lee de settings (comportamiento anterior).
Así el mismo provider sirve para Groq, Cerebras, SambaNova, OpenRouter,
Gemini y Ollama — todos hablan el mismo protocolo.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings
from app.core.schemas.llm import LLMChunk, LLMMessage, LLMResponse, TokenUsage
from app.llm.base import count_messages_tokens


def _extract_reasoning(delta) -> str | None:
    """Algunos modelos (qwen3, deepseek-r1, gpt-oss) exponen su
    razonamiento interno en un campo aparte del delta. No queremos
    enviarlo al usuario. Devolvemos el texto si existe, para poder
    descartarlo explícitamente.
    """
    for attr in ("reasoning_content", "reasoning"):
        value = getattr(delta, attr, None)
        if value:
            return str(value)
    return None


class OpenAIProvider:
    def __init__(
        self,
        *,
        name: str = "openai",
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        settings = get_settings()
        self.name = name

        key = api_key or settings.openai_api_key
        if not key:
            raise RuntimeError(f"{name}: API key no configurada")

        client_kwargs: dict = {
            "api_key": key,
            "timeout": timeout_s or settings.llm_request_timeout_s,
        }
        url = base_url if base_url is not None else settings.openai_base_url
        if url:
            client_kwargs["base_url"] = url

        self._client = AsyncOpenAI(**client_kwargs)
        self._default_model = default_model or settings.llm_default_model

    @property
    def default_model(self) -> str:
        return self._default_model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.4, max=2.0))
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": model or self._default_model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens or get_settings().max_response_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        usage = resp.usage

        # Solo `content`. El `reasoning` (qwen3, gpt-oss, etc.) se ignora.
        text = choice.message.content or ""

        return LLMResponse(
            text=text,
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason=choice.finish_reason or "stop",
            model=resp.model,
        )

    async def stream(  # type: ignore[override]
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
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
                delta = event.choices[0].delta
                # Descartamos el reasoning si existe.
                _ = _extract_reasoning(delta)
                content = delta.content or ""
                if content:
                    yield LLMChunk(delta=content)
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
        return count_messages_tokens(messages)