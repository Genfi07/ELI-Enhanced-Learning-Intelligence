"""Chunker de texto para indexación vectorial.

Diseño:
  - Cada chunk apunta a un rango de texto con ~CHUNK_SIZE_CHARS caracteres,
    con solapamiento OVERLAP_RATIO entre chunks consecutivos.
  - El algoritmo intenta cortar en fronteras naturales:
      1. Salto de párrafo (\\n\\n)
      2. Salto de línea (\\n)
      3. Fin de frase (. ! ?)
      4. Espacio
      5. Corte duro (fallback)
  - Los párrafos se procesan por separado: un párrafo corto = un chunk.
    Si un párrafo es enorme, se subdivide respetando las fronteras anteriores.
  - El resultado es una lista de `Chunk(text, meta)` donde `meta` incluye la
    página/hoja de origen y el índice del chunk dentro de esa página.

Fórmula de tokens: usamos 4 chars = 1 token (aproximación estándar en
ausencia de tokenizer. El store real hará el conteo exacto).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.observability.logging import get_logger
from app.rag.extractors.base import ExtractedPage

log = get_logger(__name__)

# Configuración por defecto
CHUNK_SIZE_CHARS = 2_400     # ~600 tokens
OVERLAP_RATIO = 0.15         # 15% de overlap
MIN_CHUNK_CHARS = 200        # chunks más cortos se fusionan con el siguiente
MAX_CHUNKS_PER_DOC = 500     # límite defensivo

# Aproximación de tokens a partir de chars
CHARS_PER_TOKEN = 4


@dataclass
class Chunk:
    text: str
    chunk_index: int
    token_count: int
    meta: dict[str, Any] = field(default_factory=dict)


class DocumentChunker:
    def __init__(
        self,
        *,
        chunk_size_chars: int = CHUNK_SIZE_CHARS,
        overlap_ratio: float = OVERLAP_RATIO,
        min_chunk_chars: int = MIN_CHUNK_CHARS,
        max_chunks: int = MAX_CHUNKS_PER_DOC,
    ) -> None:
        if not 0 <= overlap_ratio < 1:
            raise ValueError("overlap_ratio debe estar en [0, 1)")
        self.chunk_size = chunk_size_chars
        self.overlap = int(chunk_size_chars * overlap_ratio)
        self.min_chunk = min_chunk_chars
        self.max_chunks = max_chunks

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def chunk_pages(self, pages: list[ExtractedPage]) -> list[Chunk]:
        """Convierte páginas extraídas en chunks listos para embedder."""
        all_chunks: list[Chunk] = []
        global_index = 0
        for page in pages:
            text = page.text.strip()
            if not text:
                continue
            page_meta = dict(page.meta)
            pieces = self._chunk_text(text)
            for piece in pieces:
                if global_index >= self.max_chunks:
                    log.warning(
                        "chunker_max_chunks_reached", limit=self.max_chunks
                    )
                    return all_chunks
                chunk = Chunk(
                    text=piece,
                    chunk_index=global_index,
                    token_count=max(1, len(piece) // CHARS_PER_TOKEN),
                    meta={
                        **page_meta,
                        "page_chunk_index": len(
                            [c for c in all_chunks if c.meta == page_meta]
                        ),
                    },
                )
                all_chunks.append(chunk)
                global_index += 1

        # Post-proceso: fusionar chunks demasiado cortos
        return self._merge_short(all_chunks)

    # ------------------------------------------------------------------ #
    # Algoritmo de chunking
    # ------------------------------------------------------------------ #
    def _chunk_text(self, text: str) -> list[str]:
        """Divide un texto en fragmentos.

        Estrategia:
          1. Separar por párrafos (doble newline).
          2. Cada párrafo cabe en un chunk → uno.
          3. Cada párrafo demasiado grande → subdividir con overlap.
          4. Párrafos pequeños consecutivos → agrupar hasta llenar un chunk.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return []

        chunks: list[str] = []
        buffer = ""

        for para in paragraphs:
            # Párrafo pequeño: intentar acumularlo
            if len(para) <= self.chunk_size:
                candidate = (buffer + "\n\n" + para) if buffer else para
                if len(candidate) <= self.chunk_size:
                    buffer = candidate
                else:
                    if buffer:
                        chunks.append(buffer)
                    buffer = para
                continue

            # Párrafo grande: volcar buffer actual y subdividir
            if buffer:
                chunks.append(buffer)
                buffer = ""

            pieces = self._split_large_paragraph(para)
            chunks.extend(pieces)

        if buffer:
            chunks.append(buffer)

        return chunks

    def _split_large_paragraph(self, para: str) -> list[str]:
        """Divide un párrafo mayor que `chunk_size` con overlap."""
        pieces: list[str] = []
        start = 0
        length = len(para)
        while start < length:
            end = min(start + self.chunk_size, length)
            if end < length:
                # Buscar punto de corte natural entre start y end
                cut = self._find_natural_cut(para, start, end)
                if cut > start:
                    end = cut
            pieces.append(para[start:end].strip())
            if end >= length:
                break
            # Siguiente iteración: avanzar con overlap
            next_start = end - self.overlap
            if next_start <= start:
                next_start = end  # evitar bucle infinito si algo raro
            start = next_start
        return [p for p in pieces if p]

    def _find_natural_cut(self, text: str, start: int, end: int) -> int:
        """Dentro de [start, end], devuelve el mejor punto de corte.

        Prioridad: salto de párrafo > salto de línea > fin de frase > espacio.
        Si no encuentra nada útil, devuelve `end` sin tocar.
        """
        window = text[start:end]
        min_acceptable = int(len(window) * 0.5)  # no cortar demasiado pronto

        # 1. Doble salto
        idx = window.rfind("\n\n")
        if idx > min_acceptable:
            return start + idx + 2

        # 2. Salto simple
        idx = window.rfind("\n")
        if idx > min_acceptable:
            return start + idx + 1

        # 3. Fin de frase
        for punct in (". ", "! ", "? ", ".\n", ".\t"):
            idx = window.rfind(punct)
            if idx > min_acceptable:
                return start + idx + len(punct)

        # 4. Espacio
        idx = window.rfind(" ")
        if idx > min_acceptable:
            return start + idx + 1

        return end

    # ------------------------------------------------------------------ #
    # Post-procesado
    # ------------------------------------------------------------------ #
    def _merge_short(self, chunks: list[Chunk]) -> list[Chunk]:
        """Fusiona chunks demasiado cortos con el anterior si caben.

        Un chunk < min_chunk se considera ruido si puede anexarse al anterior.
        Si el resultado excedería mucho el tamaño, se deja como está.
        """
        if len(chunks) <= 1:
            return chunks

        merged: list[Chunk] = [chunks[0]]
        for c in chunks[1:]:
            last = merged[-1]
            if (
                len(last.text) < self.min_chunk
                or (len(c.text) < self.min_chunk
                    and len(last.text) + len(c.text) <= self.chunk_size * 1.2)
            ):
                combined_text = last.text + "\n\n" + c.text
                merged[-1] = Chunk(
                    text=combined_text,
                    chunk_index=last.chunk_index,
                    token_count=max(1, len(combined_text) // CHARS_PER_TOKEN),
                    meta=last.meta,
                )
            else:
                merged.append(c)

        # Renumerar índices tras fusiones
        for i, c in enumerate(merged):
            c.chunk_index = i
        return merged