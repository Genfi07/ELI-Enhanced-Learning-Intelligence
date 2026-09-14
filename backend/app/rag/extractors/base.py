"""Tipos base y registry de extractores de documentos.

Diseño:
  - Cada extractor implementa `DocumentExtractor` y sabe si puede manejar un
    MIME type (`can_handle`) y cómo extraer texto (`extract`).
  - El registry pide a cada extractor registrado si sabe manejar un mime, y
    usa el primero que diga sí.
  - Los extractores son SÍNCRONOS. El registry expone `extract_async` que
    delega a un ThreadPoolExecutor para no bloquear el event loop.
  - `ExtractedPage` representa una unidad lógica: una página de PDF, una hoja
    de Excel, un CSV entero, etc. La metadata libre permite añadir número de
    página, nombre de hoja, etc. para el chunker.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.observability.logging import get_logger

log = get_logger(__name__)


@dataclass
class ExtractedPage:
    """Una unidad de contenido extraída de un documento."""

    text: str
    # Metadata opcional: número de página, nombre de hoja, etc.
    meta: dict[str, Any] = field(default_factory=dict)


class ExtractionError(RuntimeError):
    """Error al extraer texto de un documento."""


class UnsupportedMimeType(ExtractionError):
    """No hay extractor registrado para el MIME type."""


class DocumentExtractor(Protocol):
    """Contrato de un extractor de documentos."""

    name: str
    supported_mimes: tuple[str, ...]

    def can_handle(self, mime_type: str) -> bool: ...

    def extract(self, path: Path) -> list[ExtractedPage]: ...


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="extractor")


class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: list[DocumentExtractor] = []

    def register(self, extractor: DocumentExtractor) -> None:
        self._extractors.append(extractor)

    def find(self, mime_type: str) -> DocumentExtractor | None:
        for ex in self._extractors:
            if ex.can_handle(mime_type):
                return ex
        return None

    async def extract_async(
        self, path: Path, mime_type: str
    ) -> list[ExtractedPage]:
        """Igual que extract() pero no bloquea el event loop."""
        extractor = self.find(mime_type)
        if extractor is None:
            raise UnsupportedMimeType(
                f"No hay extractor para MIME type '{mime_type}'"
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _executor, extractor.extract, path
        )

    def extract(self, path: Path, mime_type: str) -> list[ExtractedPage]:
        extractor = self.find(mime_type)
        if extractor is None:
            raise UnsupportedMimeType(
                f"No hay extractor para MIME type '{mime_type}'"
            )
        return extractor.extract(path)


def build_default_registry() -> ExtractorRegistry:
    """Registry con los extractores por defecto."""
    # Import diferido para evitar dependencias circulares
    from app.rag.extractors.docx import DocxExtractor
    from app.rag.extractors.pdf import PdfExtractor
    from app.rag.extractors.text import TextExtractor
    from app.rag.extractors.xlsx import XlsxExtractor

    reg = ExtractorRegistry()
    reg.register(PdfExtractor())
    reg.register(DocxExtractor())
    reg.register(XlsxExtractor())
    reg.register(TextExtractor())
    return reg