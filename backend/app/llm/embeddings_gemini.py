"""Embeddings vía Google Gemini (endpoint OpenAI-compatible).

Modelo: gemini-embedding-001 → 3072 dims (truncado a 1536).
API key: https://aistudio.google.com/app/apikey
Free tier: ~1.000 req/día (medido).
"""
from __future__ import annotations

import asyncio

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings
from app.llm.embeddings_batcher import BatchConfig, split_into_batches
from app.observability.logging import get_logger

log = get_logger(__name__)

TARGET_DIM = 1536

# Gemini acepta hasta 250 textos/batch y ~20.000 tokens/batch.
# Configuramos con margen de seguridad.
_BATCH_CONFIG = BatchConfig(
    max_texts_per_batch=50,
    max_tokens_per_batch=6_000,
    max_tokens_per_text=4_000,
)
MAX_CONCURRENT_BATCHES = 4


class GeminiEmbeddingsProvider:
    name = "gemini"
    dimension = TARGET_DIM

    def __init__(self) -> None:
        settings = get_settings()
        key = settings.gemini_api_key
        if not key:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        base_url = settings.gemini_base_url or (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        if not base_url.endswith("/"):
            base_url += "/"
        self._client = AsyncOpenAI(
            api_key=key,
            base_url=base_url,
            timeout=60.0,
            max_retries=0,
        )
        self._model = settings.gemini_embeddings_model or "gemini-embedding-001"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1.0, max=8.0))
    async def embed(self, text: str) -> list[float]:
        cleaned = text.strip() or " "
        resp = await self._client.embeddings.create(
            model=self._model,
            input=cleaned,
            dimensions=self.dimension,
        )
        return list(resp.data[0].embedding)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        batches = split_into_batches(texts, _BATCH_CONFIG)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)

        # Para cada texto original acumulamos los vectores de sus pedazos.
        accumulated: dict[int, list[list[float]]] = {}

        async def _one_batch(batch: list[tuple[int, str]]) -> None:
            async with semaphore:
                idxs = [i for i, _ in batch]
                inputs = [t for _, t in batch]
                resp = await self._client.embeddings.create(
                    model=self._model,
                    input=inputs,
                    dimensions=self.dimension,
                )
                for idx, d in zip(idxs, resp.data, strict=True):
                    accumulated.setdefault(idx, []).append(list(d.embedding))

        await asyncio.gather(*(_one_batch(b) for b in batches))

        # Reensamblar: promedio de pedazos por texto original.
        results: list[list[float]] = []
        for i in range(len(texts)):
            vecs = accumulated.get(i, [])
            if not vecs:
                results.append([0.0] * self.dimension)
                continue
            if len(vecs) == 1:
                results.append(vecs[0])
                continue
            # Promedio elemento a elemento.
            n = len(vecs)
            avg = [sum(v[k] for v in vecs) / n for k in range(self.dimension)]
            results.append(avg)
        return results