"""Embeddings vía Ollama local (nomic-embed-text).

nomic-embed-text produce vectores de 768 dimensiones. Nuestro schema está
fijo en 1536 (OpenAI). Aplicamos padding con ceros hasta 1536.

Optimización:
  - num_thread: ajusta al número de núcleos de CPU para paralelizar.
  - num_gpu: si hay GPU disponible, offload de capas.
  - Cliente httpx global reutilizado.
  - Semáforo de concurrencia configurable.
"""
from __future__ import annotations

import asyncio
import os

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings

OLLAMA_DIM = 768
TARGET_DIM = 1536

# Optimización: cuántos embeddings en paralelo + threads por embedding.
MAX_CONCURRENT_EMBEDS = int(os.getenv("ELI_OLLAMA_EMBED_CONCURRENCY", "8"))
# Número de hilos de CPU. Por defecto, todos los disponibles.
_OLLAMA_NUM_THREAD = int(os.getenv("ELI_OLLAMA_NUM_THREAD", "0"))
# Capas a GPU (0 = todas a CPU).
_OLLAMA_NUM_GPU = int(os.getenv("ELI_OLLAMA_NUM_GPU", "0"))

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0),
            limits=httpx.Limits(
                max_connections=32,
                max_keepalive_connections=16,
            ),
        )
    return _http_client


def _pad_to_target(vec: list[float]) -> list[float]:
    if len(vec) >= TARGET_DIM:
        return vec[:TARGET_DIM]
    return vec + [0.0] * (TARGET_DIM - len(vec))


class OllamaEmbeddingsProvider:
    name = "ollama"
    dimension = TARGET_DIM

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_embeddings_model

    def _options(self) -> dict:
        opts: dict = {}
        if _OLLAMA_NUM_THREAD > 0:
            opts["num_thread"] = _OLLAMA_NUM_THREAD
        if _OLLAMA_NUM_GPU > 0:
            opts["num_gpu"] = _OLLAMA_NUM_GPU
        return opts

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.5, max=3.0))
    async def embed(self, text: str) -> list[float]:
        client = _get_client()
        payload: dict = {"model": self._model, "prompt": text}
        opts = self._options()
        if opts:
            payload["options"] = opts
        r = await client.post(
            f"{self._base_url}/api/embeddings",
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        return _pad_to_target(list(data["embedding"]))

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_EMBEDS)

        async def _one(idx: int, text: str) -> tuple[int, list[float]]:
            async with semaphore:
                vec = await self.embed(text)
                return idx, vec

        results = await asyncio.gather(
            *(_one(i, t) for i, t in enumerate(texts))
        )
        results.sort(key=lambda x: x[0])
        return [vec for _, vec in results]