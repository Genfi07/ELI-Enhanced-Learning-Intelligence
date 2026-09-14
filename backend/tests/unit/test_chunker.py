"""Tests del DocumentChunker."""
from __future__ import annotations

import pytest

from app.rag.chunker import DocumentChunker
from app.rag.extractors.base import ExtractedPage


def _make_chunker(**kwargs) -> DocumentChunker:
    defaults = {
        "chunk_size_chars": 400,
        "overlap_ratio": 0.15,
        "min_chunk_chars": 50,
        "max_chunks": 50,
    }
    defaults.update(kwargs)
    return DocumentChunker(**defaults)


# --------------------------------------------------------------------------- #
# Casos básicos
# --------------------------------------------------------------------------- #
def test_empty_input():
    c = _make_chunker()
    assert c.chunk_pages([]) == []


def test_single_short_page():
    c = _make_chunker()
    pages = [ExtractedPage(text="Hola mundo.", meta={"page": 1})]
    chunks = c.chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].text == "Hola mundo."
    assert chunks[0].meta["page"] == 1
    assert chunks[0].chunk_index == 0


def test_page_with_empty_text_skipped():
    c = _make_chunker()
    pages = [
        ExtractedPage(text="", meta={"page": 1}),
        ExtractedPage(text="Contenido real.", meta={"page": 2}),
        ExtractedPage(text="   ", meta={"page": 3}),
    ]
    chunks = c.chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].meta["page"] == 2


# --------------------------------------------------------------------------- #
# División por párrafos
# --------------------------------------------------------------------------- #
def test_short_paragraphs_are_grouped():
    c = _make_chunker(chunk_size_chars=300)
    text = "\n\n".join(["Párrafo corto uno.", "Párrafo corto dos.", "Párrafo tres."])
    pages = [ExtractedPage(text=text)]
    chunks = c.chunk_pages(pages)
    # Tres párrafos pequeños deberían agruparse en 1 chunk
    assert len(chunks) == 1


def test_many_paragraphs_produce_multiple_chunks():
    c = _make_chunker(chunk_size_chars=200, min_chunk_chars=20)
    paragraphs = [f"Párrafo número {i} con algo de contenido extra." for i in range(10)]
    text = "\n\n".join(paragraphs)
    pages = [ExtractedPage(text=text)]
    chunks = c.chunk_pages(pages)
    assert len(chunks) >= 2
    # Los chunks deben estar numerados en orden
    assert [ch.chunk_index for ch in chunks] == list(range(len(chunks)))


# --------------------------------------------------------------------------- #
# Párrafos grandes
# --------------------------------------------------------------------------- #
def test_large_paragraph_is_split():
    c = _make_chunker(chunk_size_chars=200, overlap_ratio=0.2, min_chunk_chars=20)
    # Un solo párrafo gigante sin saltos internos
    text = "Frase muy larga número uno. " * 40
    pages = [ExtractedPage(text=text)]
    chunks = c.chunk_pages(pages)
    assert len(chunks) >= 2
    # Todos los chunks tienen longitud razonable
    for ch in chunks:
        assert len(ch.text) <= 250  # chunk_size + margen de corte natural


def test_overlap_exists_between_chunks():
    c = _make_chunker(chunk_size_chars=300, overlap_ratio=0.3, min_chunk_chars=10)
    # Texto compuesto de frases distintas para poder detectar solapamiento
    text = " ".join(f"frase{i:03d}" for i in range(200))
    pages = [ExtractedPage(text=text)]
    chunks = c.chunk_pages(pages)
    assert len(chunks) >= 2
    # Con overlap, el final del primer chunk y el inicio del segundo comparten texto
    # (Aproximación: no exigimos overlap exacto, solo que exista cierta continuidad)
    first_tail = chunks[0].text[-30:]
    second_head = chunks[1].text[:80]
    assert any(tok in second_head for tok in first_tail.split())


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def test_metadata_preserved_per_page():
    c = _make_chunker(chunk_size_chars=200, min_chunk_chars=20)
    pages = [
        ExtractedPage(text="Contenido página A. " * 15, meta={"page": 1}),
        ExtractedPage(text="Contenido página B. " * 15, meta={"page": 2}),
    ]
    chunks = c.chunk_pages(pages)
    pages_seen = {ch.meta["page"] for ch in chunks}
    assert pages_seen == {1, 2}


def test_chunks_numbered_globally():
    c = _make_chunker(chunk_size_chars=200, min_chunk_chars=20)
    pages = [
        ExtractedPage(text="Texto uno. " * 30, meta={"page": 1}),
        ExtractedPage(text="Texto dos. " * 30, meta={"page": 2}),
    ]
    chunks = c.chunk_pages(pages)
    # Índices deben ser consecutivos desde 0
    assert [ch.chunk_index for ch in chunks] == list(range(len(chunks)))


# --------------------------------------------------------------------------- #
# Límites defensivos
# --------------------------------------------------------------------------- #
def test_max_chunks_respected():
    c = _make_chunker(chunk_size_chars=100, max_chunks=3, min_chunk_chars=10)
    # Mucho texto → muchos chunks potenciales, pero cortamos a 3
    text = "\n\n".join(["Frase suficientemente larga. " * 20 for _ in range(20)])
    pages = [ExtractedPage(text=text)]
    chunks = c.chunk_pages(pages)
    assert len(chunks) <= 3


def test_token_count_estimated():
    c = _make_chunker(min_chunk_chars=10)
    pages = [ExtractedPage(text="Palabra " * 100)]
    chunks = c.chunk_pages(pages)
    assert all(ch.token_count > 0 for ch in chunks)
    # Aproximación: token_count ≈ len(text) / 4
    for ch in chunks:
        assert abs(ch.token_count - len(ch.text) // 4) <= 2


# --------------------------------------------------------------------------- #
# Fusionado de chunks cortos
# --------------------------------------------------------------------------- #
def test_short_chunks_are_merged():
    """Chunks menores a `min_chunk_chars` se fusionan con el vecino."""
    c = _make_chunker(
        chunk_size_chars=1000, min_chunk_chars=200
    )
    # Dos párrafos muy cortos separados por un salto doble → un solo chunk tras merge
    text = "Corto 1.\n\nCorto 2."
    pages = [ExtractedPage(text=text)]
    chunks = c.chunk_pages(pages)
    assert len(chunks) == 1