"""Embeddings falsos para tests y desarrollo sin API key.

Diseño:
  - Deterministas: el mismo texto → el mismo vector (hash-based).
  - Unitaria: vector normalizado a longitud 1 (así similitud coseno = producto punto).
  - Rápidos: sin red, sin coste.
  - Sin semántica real: "perro" y "can" NO serán similares. Solo sirven para
    probar el flujo, no la calidad de la recuperación.
"""
from __future__ import annotations

import hashlib
import math


FAKE_DIM = 1536  # misma dimensión que OpenAI text-embedding-3-small


class FakeEmbeddingsProvider:
    name = "fake"
    dimension = FAKE_DIM

    async def embed(self, text: str) -> list[float]:
        return self._vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        # Generamos 1536 floats a partir de hashes encadenados del texto.
        # Cada bloque de 32 bytes del SHA-256 da 32 valores pequeños.
        # Repetimos con salt para llegar a 1536.
        raw: list[float] = []
        for salt in range(0, FAKE_DIM, 32):
            h = hashlib.sha256(f"{salt}:{text}".encode("utf-8")).digest()
            raw.extend((b - 128) / 128.0 for b in h)
        raw = raw[:FAKE_DIM]

        # Normalizar a longitud 1
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]