"""FallbackEmbeddingsProvider: cadena de embeddings con rotación + caché.

Estrategia:
  - Prueba los providers en orden.
  - Si uno falla (429, conexión, timeout, 5xx) → pasa al siguiente.
  - Cache en memoria por hash del texto: la misma cadena no re-llama APIs.
  - Errores no recuperables (401 auth) abortan sin rotar.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict

from app.core.contracts.embeddings import EmbeddingsProvider
from app.observability.logging import get_logger

log = get_logger(__name__)

MAX_CACHE_ENTRIES = 10_000


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


class EmbeddingsCache:
    """LRU simple: cuando se llena, expulsa el más antiguo."""

    def __init__(self, max_size: int = MAX_CACHE_ENTRIES) -> None:
        self._data: OrderedDict[str, list[float]] = OrderedDict()
        self._max = max_size

    def get(self, key: str) -> list[float] | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: str, value: list[float]) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)


_cache = EmbeddingsCache()


def _should_rotate(exc: Exception) -> bool:
    """True si el error justifica probar con el siguiente proveedor."""
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        RateLimitError,
    )

    if isinstance(exc, (AuthenticationError, BadRequestError)):
        return False
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500 or exc.status_code == 429
    return True


class FallbackEmbeddingsProvider:
    def __init__(self, providers: list[EmbeddingsProvider]) -> None:
        if not providers:
            raise ValueError("FallbackEmbeddingsProvider requiere al menos un provider")
        self.providers = providers
        names = ",".join(getattr(p, "name", "?") for p in providers)
        self.name = f"fallback({names})"
        self.dimension = providers[0].dimension

    async def embed(self, text: str) -> list[float]:
        key = _hash_text(text)
        cached = _cache.get(key)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        for provider in self.providers:
            try:
                vec = await provider.embed(text)
                _cache.put(key, vec)
                return vec
            except Exception as exc:
                if not _should_rotate(exc):
                    raise
                log.warning(
                    "embeddings_provider_switching",
                    failed=provider.name,
                    error=str(exc)[:160],
                )
                last_error = exc
                continue
        assert last_error is not None
        raise last_error

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        for i, t in enumerate(texts):
            cached = _cache.get(_hash_text(t))
            if cached is not None:
                results[i] = cached
            else:
                missing_indices.append(i)

        if not missing_indices:
            return results  # type: ignore[return-value]

        missing_texts = [texts[i] for i in missing_indices]
        new_vecs: list[list[float]] | None = None
        last_error: Exception | None = None

        for provider in self.providers:
            try:
                new_vecs = await provider.embed_batch(missing_texts)
                break
            except Exception as exc:
                if not _should_rotate(exc):
                    raise
                log.warning(
                    "embeddings_batch_provider_switching",
                    failed=provider.name,
                    batch_size=len(missing_texts),
                    error=str(exc)[:160],
                )
                last_error = exc
                continue

        if new_vecs is None:
            assert last_error is not None
            raise last_error

        for idx, vec in zip(missing_indices, new_vecs, strict=True):
            _cache.put(_hash_text(texts[idx]), vec)
            results[idx] = vec

        return results  # type: ignore[return-value]