"""Extractor de XLSX con openpyxl.

Política:
  - Cada hoja se trata como UNA página. El meta indica el nombre.
  - Cada fila se serializa como celdas separadas por tabulador.
  - Solo valores con `data_only=True` (valores calculados, no fórmulas).
  - Las hojas vacías se omiten.
  - Cortamos a un máximo de filas por hoja para no explotar con Excels
    gigantes. Configurable.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from app.observability.logging import get_logger
from app.rag.extractors.base import ExtractedPage, ExtractionError

log = get_logger(__name__)

# Límite defensivo: XLSX gigantes se truncan. Ajustable.
MAX_ROWS_PER_SHEET = 5_000
MAX_COLS_PER_ROW = 50


class XlsxExtractor:
    name = "xlsx"
    supported_mimes = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",  # legacy .xls (openpyxl no lo abre; fallará)
    )

    def can_handle(self, mime_type: str) -> bool:
        return mime_type in self.supported_mimes

    def extract(self, path: Path) -> list[ExtractedPage]:
        if not path.is_file():
            raise ExtractionError(f"archivo no encontrado: {path}")
        try:
            wb = load_workbook(str(path), data_only=True, read_only=True)
        except Exception as exc:
            raise ExtractionError(f"XLSX inválido o corrupto: {exc}") from exc

        pages: list[ExtractedPage] = []
        try:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows_text: list[str] = []
                row_count = 0
                for row in ws.iter_rows(values_only=True):
                    if row_count >= MAX_ROWS_PER_SHEET:
                        log.info(
                            "xlsx_sheet_truncated",
                            sheet=sheet_name,
                            max_rows=MAX_ROWS_PER_SHEET,
                        )
                        break
                    cells = []
                    for cell in row[:MAX_COLS_PER_ROW]:
                        if cell is None:
                            cells.append("")
                        else:
                            cells.append(str(cell))
                    # Saltar filas completamente vacías
                    if any(c for c in cells):
                        rows_text.append("\t".join(cells))
                        row_count += 1
                if rows_text:
                    pages.append(
                        ExtractedPage(
                            text="\n".join(rows_text),
                            meta={"sheet": sheet_name, "rows": row_count},
                        )
                    )
        finally:
            wb.close()

        return pages