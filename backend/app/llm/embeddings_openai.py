"""Embeddings reales vía OpenAI.

Modelo por defecto: text-embedding-3-small (1536 dims, ~$0.02 por millón de tokens).
Se puede cambiar a text-embedding-3-large (3072 dims) con un cambio de config,
pero eso requiere migración del schema (dim fija).
"""
from __future__ import annotations

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings


DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536


class OpenAIEmbeddingsProvider:
    name = "openai"
    dimension = DEFAULT_DIM

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        settings = get_settings()
        key = api_key or settings.openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY no configurada para embeddings")
        self._client = AsyncOpenAI(api_key=key, timeout=settings.llm_request_timeout_s)
        self._model = model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.4, max=2.0))
    async def embed(self, text: str) -> list[float]:
        result = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        return list(result.data[0].embedding)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.4, max=2.0))
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [list(item.embedding) for item in result.data]