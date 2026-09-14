"""Extractor de texto plano: TXT, MD, JSON, YAML.

Política de detección de encoding:
  1. Si hay BOM UTF-16 (LE o BE) → decodificar como utf-16.
  2. Si hay BOM UTF-8 → decodificar como utf-8-sig.
  3. Intentar utf-8 estricto.
  4. Fallback a latin-1 (nunca falla, siempre produce texto).

NUNCA intentamos utf-16 sin BOM: prácticamente cualquier par de bytes
"decodifica" como utf-16 a basura silenciosa.

Todo el archivo se trata como UNA página. Cortamos a un máximo de chars
para evitar archivos enormes en el pipeline.
"""
from __future__ import annotations

from pathlib import Path

from app.observability.logging import get_logger
from app.rag.extractors.base import ExtractedPage, ExtractionError

log = get_logger(__name__)

MAX_CHARS = 2_000_000  # ~500k tokens, suficiente para cualquier caso razonable


class TextExtractor:
    name = "text"
    supported_mimes = (
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/json",
        "text/yaml",
        "application/x-yaml",
        "text/csv",       # CSV plano: lo tratamos como texto (una página)
        "text/tab-separated-values",
    )

    def can_handle(self, mime_type: str) -> bool:
        return mime_type in self.supported_mimes

    def extract(self, path: Path) -> list[ExtractedPage]:
        if not path.is_file():
            raise ExtractionError(f"archivo no encontrado: {path}")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ExtractionError(f"no se pudo leer el archivo: {exc}") from exc

        text = self._decode(raw)
        text = text[:MAX_CHARS].strip()
        if not text:
            return []

        return [
            ExtractedPage(
                text=text,
                meta={"chars": len(text), "truncated": len(text) >= MAX_CHARS},
            )
        ]

    @staticmethod
    def _decode(raw: bytes) -> str:
        # 1. BOM UTF-16
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            try:
                return raw.decode("utf-16")
            except UnicodeDecodeError:
                pass

        # 2. BOM UTF-8
        if raw.startswith(b"\xef\xbb\xbf"):
            try:
                return raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                pass

        # 3. UTF-8 estricto
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # 4. Fallback: latin-1 (nunca falla). Puede producir caracteres raros
        #    pero nunca lanza excepción ni pierde datos.
        return raw.decode("latin-1")