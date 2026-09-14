"""Extractor de DOCX con python-docx.

Política:
  - Todo el documento se trata como UNA página (los DOCX no tienen páginas
    físicas en el formato; las páginas son una decisión de render).
  - Recorremos párrafos y tablas en orden.
  - Las tablas se serializan como texto tabulado por filas.
  - El meta indica cuántos párrafos y tablas se procesaron.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError

from app.observability.logging import get_logger
from app.rag.extractors.base import ExtractedPage, ExtractionError

log = get_logger(__name__)


class DocxExtractor:
    name = "docx"
    supported_mimes = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",  # legacy .doc (best effort — python-docx puede no abrirlo)
    )

    def can_handle(self, mime_type: str) -> bool:
        return mime_type in self.supported_mimes

    def extract(self, path: Path) -> list[ExtractedPage]:
        if not path.is_file():
            raise ExtractionError(f"archivo no encontrado: {path}")
        try:
            doc = DocxDocument(str(path))
        except PackageNotFoundError as exc:
            raise ExtractionError(f"DOCX inválido o corrupto: {exc}") from exc

        parts: list[str] = []
        paragraphs = 0
        tables = 0

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                parts.append(text)
                paragraphs += 1

        for table in doc.tables:
            rows: list[str] = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(" | ".join(cells))
            if rows:
                parts.append("\n".join(rows))
                tables += 1

        full_text = "\n\n".join(parts)
        if not full_text:
            return []

        return [
            ExtractedPage(
                text=full_text,
                meta={
                    "paragraphs": paragraphs,
                    "tables": tables,
                },
            )
        ]