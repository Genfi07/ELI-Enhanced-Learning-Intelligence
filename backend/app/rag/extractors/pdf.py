"""Extractor de PDFs con pdfplumber.

Política:
  - Extrae texto por página. Si una página está vacía (PDF de imágenes sin
    capa de texto), devuelve un ExtractedPage con texto vacío y meta
    {"empty_page": True}. El chunker los ignora.
  - No hacemos OCR: si todo el PDF está vacío, devolvemos lista vacía.
  - El meta incluye `page` (1-indexed) para trazabilidad.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from app.observability.logging import get_logger
from app.rag.extractors.base import ExtractedPage, ExtractionError

log = get_logger(__name__)


class PdfExtractor:
    name = "pdf"
    supported_mimes = ("application/pdf",)

    def can_handle(self, mime_type: str) -> bool:
        return mime_type in self.supported_mimes

    def extract(self, path: Path) -> list[ExtractedPage]:
        if not path.is_file():
            raise ExtractionError(f"archivo no encontrado: {path}")
        pages: list[ExtractedPage] = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    try:
                        text = page.extract_text() or ""
                    except Exception as exc:
                        log.warning(
                            "pdf_page_extract_failed",
                            page=i,
                            error=str(exc),
                        )
                        text = ""
                    pages.append(
                        ExtractedPage(
                            text=text.strip(),
                            meta={"page": i, "empty_page": not bool(text.strip())},
                        )
                    )
        except Exception as exc:
            raise ExtractionError(f"fallo al abrir PDF: {exc}") from exc

        # Sin texto útil en ninguna página → no devolvemos nada
        if not any(p.text for p in pages):
            log.info("pdf_without_extractable_text", path=str(path))
        return pages