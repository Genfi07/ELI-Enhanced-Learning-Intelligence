"""Extractor de XLSX con openpyxl.

Notas críticas:
  - Usamos `read_only=False` porque con `read_only=True` openpyxl sólo
    devuelve la primera fila cuando el Excel tiene celdas combinadas o
    filas con estructuras irregulares (bug conocido).
  - El header NO es siempre la primera fila: puede haber filas de
    "Filtros aplicados: ..." antes. Detectamos el header como la fila
    con más celdas no vacías dentro de las primeras MAX_HEADER_SCAN filas.
  - Cada hoja se divide en BLOQUES de ROWS_PER_PAGE filas de datos.
  - El header se repite al inicio de cada bloque.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from app.observability.logging import get_logger
from app.rag.extractors.base import ExtractedPage, ExtractionError

log = get_logger(__name__)

MAX_ROWS_PER_SHEET = 5_000
MAX_COLS_PER_ROW = 50

# Filas por bloque (antes de añadir el header).
ROWS_PER_PAGE = 50

# Cuántas filas iniciales inspeccionamos para detectar el header.
# El header suele estar en las primeras 5 filas de un Excel con metadatos.
MAX_HEADER_SCAN = 5


class XlsxExtractor:
    name = "xlsx"
    supported_mimes = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    )

    def can_handle(self, mime_type: str) -> bool:
        return mime_type in self.supported_mimes

    def extract(self, path: Path) -> list[ExtractedPage]:
        if not path.is_file():
            raise ExtractionError(f"archivo no encontrado: {path}")
        try:
            # read_only=False es CRÍTICO: read_only=True se atasca con celdas
            # combinadas y sólo devuelve la primera fila.
            wb = load_workbook(str(path), data_only=True, read_only=False)
        except Exception as exc:
            raise ExtractionError(f"XLSX inválido o corrupto: {exc}") from exc

        pages: list[ExtractedPage] = []
        try:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                pages.extend(self._extract_sheet(ws, sheet_name))
        finally:
            wb.close()

        return pages

    def _extract_sheet(self, ws, sheet_name: str) -> list[ExtractedPage]:
        # Leer todas las filas como listas de strings normalizados.
        raw_rows: list[list[str]] = []
        for row in ws.iter_rows(values_only=True):
            cells: list[str] = []
            for cell in row[:MAX_COLS_PER_ROW]:
                if cell is None:
                    cells.append("")
                else:
                    # Normalizar saltos internos
                    cells.append(
                        str(cell).replace("\n", " ").replace("\t", " ").strip()
                    )
            raw_rows.append(cells)
            if len(raw_rows) >= MAX_ROWS_PER_SHEET + MAX_HEADER_SCAN:
                log.info(
                    "xlsx_sheet_truncated",
                    sheet=sheet_name,
                    max_rows=MAX_ROWS_PER_SHEET,
                )
                break

        if not raw_rows:
            return []

        # Detectar el header: la fila con MÁS celdas no vacías en las
        # primeras MAX_HEADER_SCAN filas.
        header_idx = 0
        best_count = -1
        for i, row in enumerate(raw_rows[:MAX_HEADER_SCAN]):
            non_empty = sum(1 for c in row if c)
            if non_empty > best_count:
                best_count = non_empty
                header_idx = i

        header_row = raw_rows[header_idx]
        header_text = "\t".join(header_row)

        # Filas de datos = todo lo que viene después del header y no está vacío.
        data_rows: list[str] = []
        for row in raw_rows[header_idx + 1 :]:
            if any(c for c in row):
                data_rows.append("\t".join(row))

        if not data_rows:
            # Solo header, sin datos
            return [
                ExtractedPage(
                    text=header_text,
                    meta={"sheet": sheet_name, "rows": 0, "block": 0},
                )
            ]

        # Emitir bloques de ROWS_PER_PAGE, con header repetido.
        pages: list[ExtractedPage] = []
        for block_idx, start in enumerate(range(0, len(data_rows), ROWS_PER_PAGE)):
            block = data_rows[start : start + ROWS_PER_PAGE]
            text = "\n".join([header_text] + block)
            pages.append(
                ExtractedPage(
                    text=text,
                    meta={
                        "sheet": sheet_name,
                        "rows": len(block),
                        "block": block_idx,
                        "row_start": start + 1,
                        "row_end": start + len(block),
                        "header_row_index": header_idx,
                    },
                )
            )

        log.info(
            "xlsx_extracted",
            sheet=sheet_name,
            rows=len(data_rows),
            blocks=len(pages),
            header_row_index=header_idx,
        )
        return pages