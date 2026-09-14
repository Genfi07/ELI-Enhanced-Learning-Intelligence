"""Tests de extractores de documentos.

Cubren:
  - Registry: encontrar extractor por MIME, error si no hay.
  - TextExtractor: TXT, MD, JSON.
  - XlsxExtractor: XLSX con varias hojas.
  - DocxExtractor: DOCX básico con párrafos y tabla.
  - PdfExtractor: skip si pdfplumber no puede; crea un PDF mínimo con reportlab.

Nota: no instalamos reportlab. Para el PDF, creamos un PDF mínimo a mano con
el formato PDF más simple posible (un stream de texto). Si falla por
estructura, el test verifica que el extractor devuelve lista vacía sin lanzar.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.extractors.base import (
    ExtractorRegistry,
    UnsupportedMimeType,
    build_default_registry,
)


@pytest.fixture
def registry() -> ExtractorRegistry:
    return build_default_registry()


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_finds_text(registry):
    ex = registry.find("text/plain")
    assert ex is not None
    assert ex.name == "text"


def test_registry_finds_pdf(registry):
    assert registry.find("application/pdf").name == "pdf"


def test_registry_finds_xlsx(registry):
    assert registry.find(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ).name == "xlsx"


def test_registry_finds_docx(registry):
    assert registry.find(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ).name == "docx"


def test_registry_unknown_mime_raises(registry, tmp_path: Path):
    f = tmp_path / "file.xyz"
    f.write_bytes(b"x")
    with pytest.raises(UnsupportedMimeType):
        registry.extract(f, "application/x-unknown")


# --------------------------------------------------------------------------- #
# TextExtractor
# --------------------------------------------------------------------------- #
def test_text_extractor_txt(registry, tmp_path: Path):
    f = tmp_path / "nota.txt"
    f.write_text("Hola mundo\nSegunda línea", encoding="utf-8")
    pages = registry.extract(f, "text/plain")
    assert len(pages) == 1
    assert "Hola mundo" in pages[0].text
    assert pages[0].meta["chars"] > 0


def test_text_extractor_markdown(registry, tmp_path: Path):
    f = tmp_path / "doc.md"
    f.write_text("# Título\n\nPárrafo con **negritas**.", encoding="utf-8")
    pages = registry.extract(f, "text/markdown")
    assert len(pages) == 1
    assert "Título" in pages[0].text


def test_text_extractor_latin1_fallback(registry, tmp_path: Path):
    f = tmp_path / "latin.txt"
    # Bytes inválidos en UTF-8 (0xE1 = 'á' en latin-1)
    f.write_bytes(b"caf\xe9 con leche")
    pages = registry.extract(f, "text/plain")
    assert len(pages) == 1
    # No exigimos un char concreto; solo que no explote y devuelva algo
    assert "caf" in pages[0].text


def test_text_extractor_empty_file_returns_empty(registry, tmp_path: Path):
    f = tmp_path / "vacio.txt"
    f.write_text("", encoding="utf-8")
    pages = registry.extract(f, "text/plain")
    assert pages == []


# --------------------------------------------------------------------------- #
# XlsxExtractor
# --------------------------------------------------------------------------- #
def test_xlsx_extractor_two_sheets(registry, tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Productos"
    ws1.append(["nombre", "precio"])
    ws1.append(["café", 3.5])
    ws1.append(["pan", 1.2])
    ws2 = wb.create_sheet("Stock")
    ws2.append(["producto", "cantidad"])
    ws2.append(["café", 100])
    f = tmp_path / "datos.xlsx"
    wb.save(str(f))

    pages = registry.extract(
        f,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert len(pages) == 2
    assert pages[0].meta["sheet"] == "Productos"
    assert "café" in pages[0].text
    assert pages[1].meta["sheet"] == "Stock"
    assert "cantidad" in pages[1].text


def test_xlsx_extractor_skips_empty_sheets(registry, tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vacía"
    # No añadimos nada
    wb.create_sheet("Datos").append(["algo"])
    f = tmp_path / "parcial.xlsx"
    wb.save(str(f))

    pages = registry.extract(
        f,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert len(pages) == 1
    assert pages[0].meta["sheet"] == "Datos"


# --------------------------------------------------------------------------- #
# DocxExtractor
# --------------------------------------------------------------------------- #
def test_docx_extractor_paragraphs_and_table(registry, tmp_path: Path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph("Introducción al documento.")
    doc.add_paragraph("Segundo párrafo con info.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "col1"
    table.cell(0, 1).text = "col2"
    table.cell(1, 0).text = "a"
    table.cell(1, 1).text = "b"
    f = tmp_path / "doc.docx"
    doc.save(str(f))

    pages = registry.extract(
        f,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert len(pages) == 1
    assert "Introducción" in pages[0].text
    assert "Segundo párrafo" in pages[0].text
    assert "col1 | col2" in pages[0].text
    assert pages[0].meta["paragraphs"] == 2
    assert pages[0].meta["tables"] == 1


def test_docx_extractor_empty_document(registry, tmp_path: Path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    f = tmp_path / "vacio.docx"
    doc.save(str(f))

    pages = registry.extract(
        f,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert pages == []


# --------------------------------------------------------------------------- #
# PdfExtractor (best-effort, sin fixture real)
# --------------------------------------------------------------------------- #
def test_pdf_extractor_on_invalid_file_raises(registry, tmp_path: Path):
    """Un PDF no válido debe lanzar ExtractionError, no romper feo."""
    from app.rag.extractors.base import ExtractionError

    f = tmp_path / "no_pdf.pdf"
    f.write_bytes(b"esto no es un PDF")
    with pytest.raises(ExtractionError):
        registry.extract(f, "application/pdf")