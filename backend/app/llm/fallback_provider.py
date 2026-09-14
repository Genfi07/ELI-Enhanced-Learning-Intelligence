"""FallbackLLMProvider: cadena de proveedores con rotación automática.

Estrategia:
  - Se prueban los providers en orden de prioridad.
  - Se rota al siguiente en errores RECUPERABLES:
      * RateLimitError (429)
      * APIConnectionError
      * APITimeoutError
      * APIStatusError con status >= 500
  - NO se rota en errores NO recuperables (todos fallarían igual):
      * AuthenticationError (401) → la key está mal
      * BadRequestError (400) → el request está mal
  - En streaming, solo se rota si el fallo ocurre ANTES de emitir el
    primer chunk. Si ya empezamos a responder, no podemos cortar a mitad.
  - Cada provider usa su propio `default_model`. El `FallbackLLMProvider`
    NO pasa modelo — cada provider decide el suyo.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMChunk, LLMMessage, LLMResponse
from app.observability.logging import get_logger

log = get_logger(__name__)


def _should_rotate(exc: Exception) -> bool:
    """True si el error justifica probar con el siguiente proveedor."""
    if isinstance(exc, (AuthenticationError, BadRequestError)):
        return False
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False


class FallbackLLMProvider:
    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackLLMProvider requiere al menos un provider")
        self.providers = providers
        names = ",".join(getattr(p, "name", "?") for p in providers)
        self.name = f"fallback({names})"

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> LLMResponse:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                # Cada provider usa su propio modelo.
                provider_model = getattr(provider, "default_model", None) or model
                return await provider.generate(
                    messages,
                    model=provider_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            except Exception as exc:
                if not _should_rotate(exc):
                    raise
                log.warning(
                    "fallback_provider_switching",
                    failed=provider.name,
                    error=str(exc)[:200],
                )
                last_error = exc
                continue
        assert last_error is not None
        raise last_error

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMChunk]:
        last_error: Exception | None = None
        for provider in self.providers:
            yielded_any = False
            try:
                provider_model = getattr(provider, "default_model", None) or model
                async for chunk in provider.stream(
                    messages,
                    model=provider_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yielded_any = True
                    yield chunk
                return
            except Exception as exc:
                if not _should_rotate(exc):
                    raise
                if yielded_any:
                    # Ya empezamos a streamear: no se puede rotar.
                    log.warning(
                        "fallback_stream_failed_after_start",
                        provider=provider.name,
                        error=str(exc)[:200],
                    )
                    raise
                log.warning(
                    "fallback_provider_switching",
                    failed=provider.name,
                    error=str(exc)[:200],
                )
                last_error = exc
                continue
        if last_error is not None:
            raise last_error

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        if not self.providers:
            return 0
        return self.providers[0].count_tokens(messages)