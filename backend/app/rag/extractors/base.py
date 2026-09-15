"""Tipos base y registry de extractores de documentos.

Diseño:
  - Cada extractor implementa `DocumentExtractor` y sabe si puede manejar
    un MIME type (`can_handle`) y cómo extraer texto (`extract`).
  - El registry pide a cada extractor registrado si sabe manejar un mime,
    y usa el primero que diga sí.
  - Los extractores son SÍNCRONOS por defecto. El registry expone
    `extract_async` que delega a un ThreadPoolExecutor.
  - Si un extractor implementa `AsyncDocumentExtractor` (con `extract_async`),
    el registry lo detecta y usa su versión asíncrona directamente.
    Esto es necesario para extractores que llaman a APIs de visión (Gemini).

`ExtractedPage` representa una unidad lógica: una página de PDF, una hoja
de Excel, una imagen completa, etc.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.observability.logging import get_logger

log = get_logger(__name__)


@dataclass
class ExtractedPage:
    """Una unidad de contenido extraída de un documento."""
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


class ExtractionError(RuntimeError):
    """Error al extraer texto de un documento."""


class UnsupportedMimeType(ExtractionError):
    """No hay extractor registrado para el MIME type."""


@runtime_checkable
class DocumentExtractor(Protocol):
    """Contrato de un extractor síncrono."""
    name: str
    supported_mimes: tuple[str, ...]

    def can_handle(self, mime_type: str) -> bool: ...
    def extract(self, path: Path) -> list[ExtractedPage]: ...


@runtime_checkable
class AsyncDocumentExtractor(Protocol):
    """Contrato de un extractor asíncrono (llama a APIs externas)."""
    name: str
    supported_mimes: tuple[str, ...]

    def can_handle(self, mime_type: str) -> bool: ...
    async def extract_async(self, path: Path) -> list[ExtractedPage]: ...


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="extractor")


class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: list[DocumentExtractor | AsyncDocumentExtractor] = []

    def register(self, extractor: DocumentExtractor | AsyncDocumentExtractor) -> None:
        self._extractors.append(extractor)

    def find(self, mime_type: str) -> DocumentExtractor | AsyncDocumentExtractor | None:
        for ex in self._extractors:
            if ex.can_handle(mime_type):
                return ex
        return None

    async def extract_async(self, path: Path, mime_type: str) -> list[ExtractedPage]:
        """Extrae texto sin bloquear el event loop.

        Si el extractor implementa `extract_async`, se llama directamente.
        Si es síncrono, se ejecuta en ThreadPoolExecutor.
        """
        extractor = self.find(mime_type)
        if extractor is None:
            raise UnsupportedMimeType(
                f"No hay extractor para MIME type '{mime_type}'"
            )

        # Detección dinámica: ¿es asíncrono?
        if hasattr(extractor, "extract_async") and callable(
            getattr(extractor, "extract_async")
        ):
            return await extractor.extract_async(path)  # type: ignore[union-attr]

        # Fallback síncrono en thread
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, extractor.extract, path)  # type: ignore[union-attr]

    def extract(self, path: Path, mime_type: str) -> list[ExtractedPage]:
        extractor = self.find(mime_type)
        if extractor is None:
            raise UnsupportedMimeType(
                f"No hay extractor para MIME type '{mime_type}'"
            )
        return extractor.extract(path)  # type: ignore[union-attr]


def build_default_registry() -> ExtractorRegistry:
    """Registry con los extractores por defecto."""
    from app.rag.extractors.docx import DocxExtractor
    from app.rag.extractors.image_extractor import ImageExtractor
    from app.rag.extractors.pdf import PdfExtractor
    from app.rag.extractors.text import TextExtractor
    from app.rag.extractors.xlsx import XlsxExtractor

    reg = ExtractorRegistry()
    reg.register(PdfExtractor())
    reg.register(DocxExtractor())
    reg.register(XlsxExtractor())
    reg.register(TextExtractor())
    reg.register(ImageExtractor())
    return reg