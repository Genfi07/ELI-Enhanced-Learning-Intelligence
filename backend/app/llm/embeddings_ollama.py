"""Embeddings vía Ollama local (nomic-embed-text).

nomic-embed-text produce vectores de 768 dimensiones. Nuestro schema está
fijo en 1536 (OpenAI). Aplicamos padding con ceros hasta 1536: no altera
la similitud coseno porque los ceros añadidos contribuyen 0 al producto
punto y no modifican la norma del vector.
"""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings

OLLAMA_DIM = 768
TARGET_DIM = 1536


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

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.5, max=3.0))
    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
            )
            r.raise_for_status()
            data = r.json()
        return _pad_to_target(list(data["embedding"]))

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama no tiene batch nativo. Secuencial.
        return [await self.embed(t) for t in texts]