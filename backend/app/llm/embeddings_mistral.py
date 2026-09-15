"""Embeddings vía Mistral AI (endpoint OpenAI-compatible).

Modelo: mistral-embed → 1024 dims (padded a 1536).
API key: https://console.mistral.ai/api-keys
Free tier: ~1B tokens/mes compartidos.
"""
from __future__ import annotations

import asyncio

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings
from app.llm.embeddings_batcher import BatchConfig, split_into_batches
from app.observability.logging import get_logger

log = get_logger(__name__)

MISTRAL_DIM = 1024
TARGET_DIM = 1536

_BATCH_CONFIG = BatchConfig(
    max_texts_per_batch=50,
    max_tokens_per_batch=6_000,
    max_tokens_per_text=4_000,
)
MAX_CONCURRENT_BATCHES = 3


def _pad_to_target(vec: list[float]) -> list[float]:
    if len(vec) >= TARGET_DIM:
        return vec[:TARGET_DIM]
    return vec + [0.0] * (TARGET_DIM - len(vec))


class MistralEmbeddingsProvider:
    name = "mistral-embed"
    dimension = TARGET_DIM

    def __init__(self) -> None:
        settings = get_settings()
        key = settings.mistral_api_key
        if not key:
            raise RuntimeError("MISTRAL_API_KEY no configurada")
        self._client = AsyncOpenAI(
            api_key=key,
            base_url="https://api.mistral.ai/v1",
            timeout=60.0,
            max_retries=0,
        )
        self._model = "mistral-embed"

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1.0, max=6.0))
    async def embed(self, text: str) -> list[float]:
        cleaned = text.strip() or " "
        resp = await self._client.embeddings.create(
            model=self._model,
            input=cleaned,
        )
        return _pad_to_target(list(resp.data[0].embedding))

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        batches = split_into_batches(texts, _BATCH_CONFIG)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
        accumulated: dict[int, list[list[float]]] = {}

        async def _one_batch(batch: list[tuple[int, str]]) -> None:
            async with semaphore:
                idxs = [i for i, _ in batch]
                inputs = [t for _, t in batch]
                resp = await self._client.embeddings.create(
                    model=self._model,
                    input=inputs,
                )
                for idx, d in zip(idxs, resp.data, strict=True):
                    accumulated.setdefault(idx, []).append(
                        _pad_to_target(list(d.embedding))
                    )

        await asyncio.gather(*(_one_batch(b) for b in batches))

        results: list[list[float]] = []
        for i in range(len(texts)):
            vecs = accumulated.get(i, [])
            if not vecs:
                results.append([0.0] * TARGET_DIM)
            elif len(vecs) == 1:
                results.append(vecs[0])
            else:
                n = len(vecs)
                avg = [sum(v[k] for v in vecs) / n for k in range(TARGET_DIM)]
                results.append(avg)
        return results