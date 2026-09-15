"""Batcher común para proveedores de embeddings.

Divide listas de textos en batches que respetan DOS límites:
  - Número de textos por batch (los proveedores limitan count).
  - Tokens totales por batch (los proveedores limitan tokens).

Además trocea textos individuales que excedan el máximo de tokens
por texto (algunos providers rechazan textos >8192 tokens).

Estimación de tokens: 1 token ≈ 4 caracteres (estándar para español
e inglés). No es exacta pero es suficiente para respetar márgenes.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.observability.logging import get_logger

log = get_logger(__name__)


def estimate_tokens(text: str) -> int:
    """Estimación rápida: 1 token ≈ 4 caracteres."""
    return max(1, len(text) // 4)


@dataclass
class BatchConfig:
    max_texts_per_batch: int = 50
    max_tokens_per_batch: int = 6_000
    max_tokens_per_text: int = 4_000


def split_text_if_too_long(text: str, max_tokens: int) -> list[str]:
    """Trocea un texto que excede `max_tokens` en pedazos contiguos.

    Si el texto cabe, devuelve [text]. Si no, lo parte en pedazos
    aproximadamente iguales sin overlap (los embeddings de cada
    pedazo se promedian después, en `split_into_batches`).
    """
    if estimate_tokens(text) <= max_tokens:
        return [text]

    max_chars = max_tokens * 4
    pieces: list[str] = []
    for i in range(0, len(text), max_chars):
        piece = text[i : i + max_chars]
        if piece.strip():
            pieces.append(piece)
    return pieces if pieces else [text[:max_chars]]


def split_into_batches(
    texts: list[str],
    config: BatchConfig | None = None,
) -> list[list[tuple[int, str]]]:
    """Divide textos en batches. Devuelve lista de batches, donde cada
    batch es una lista de (indice_original, texto).

    Un texto largo puede aparecer múltiples veces (troceado) en el
    resultado. El llamador debe promediar los vectores de los pedazos
    para reconstruir el vector del texto original.

    Los textos vacíos se reemplazan por un espacio para evitar errores
    de providers que rechazan strings vacíos.
    """
    cfg = config or BatchConfig()

    # 1) Normalizar y trocear textos demasiado largos.
    expanded: list[tuple[int, str]] = []
    for i, t in enumerate(texts):
        cleaned = t.strip() or " "
        for piece in split_text_if_too_long(cleaned, cfg.max_tokens_per_text):
            expanded.append((i, piece))

    # 2) Agrupar en batches respetando ambas cuotas.
    batches: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_tokens = 0

    for idx, text in expanded:
        t_tokens = estimate_tokens(text)
        too_many_texts = len(current) >= cfg.max_texts_per_batch
        too_many_tokens = (
            current and current_tokens + t_tokens > cfg.max_tokens_per_batch
        )
        if too_many_texts or too_many_tokens:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append((idx, text))
        current_tokens += t_tokens

    if current:
        batches.append(current)

    log.debug(
        "embeddings_batched",
        n_texts=len(texts),
        n_expanded=len(expanded),
        n_batches=len(batches),
    )
    return batches