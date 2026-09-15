"""Extractor de imágenes usando Gemini Vision (OCR + descripción).

Flujo:
  1. Lee la imagen del disco como bytes.
  2. La codifica en base64 y la envía a Gemini en formato OpenAI-compatible.
  3. Gemini transcribe el texto (OCR) o describe la imagen si no hay texto.
  4. Devuelve el resultado como una ExtractedPage.

Modelo por defecto: gemini-3.5-flash-lite (el mismo del chat, ya configurado).
Si el modelo no soporta visión, la llamada fallará y el ingestor marcará
el documento como FAILED con el error.

MIME types soportados:
  - image/png
  - image/jpeg
  - image/jpg (alias de jpeg)
  - image/webp
  - image/gif
  - image/heic / image/heif
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.observability.logging import get_logger
from app.rag.extractors.base import ExtractedPage, ExtractionError

log = get_logger(__name__)

SUPPORTED_MIMES = (
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
)

# Tamaño máximo del archivo. Gemini acepta hasta 20MB inline.
MAX_IMAGE_BYTES = 20 * 1024 * 1024

EXTRACTION_PROMPT = """\
Analiza esta imagen. Tu trabajo es extraer todo su contenido textual de
forma literal (OCR). Si la imagen contiene tablas, transcríbelas en formato
Markdown. Si contiene diagramas o gráficos, describe su estructura y
contenido. Si no contiene texto reconocible, describe la imagen en detalle.

Reglas:
  - Devuelve SOLO el contenido extraído. Sin introducciones ni comentarios.
  - Si hay texto, transcríbelo exactamente como aparece.
  - Si hay varios idiomas, mantén el original y, si aporta valor, añade
    traducción al español entre corchetes.
  - Si la imagen es una captura de pantalla, extrae todo el texto visible.
  - Si la imagen es una foto de un documento, extrae el texto del documento.
"""


class ImageExtractor:
    """Extractor asíncrono que usa Gemini Vision para OCR y descripción."""

    name = "image"
    supported_mimes = SUPPORTED_MIMES

    def __init__(self) -> None:
        settings = get_settings()
        key = settings.gemini_api_key
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY no configurada. Consíguela en "
                "https://aistudio.google.com/app/apikey"
            )
        base_url = settings.gemini_base_url or (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        if not base_url.endswith("/"):
            base_url += "/"

        self._client = AsyncOpenAI(
            api_key=key,
            base_url=base_url,
            timeout=120.0,  # imágenes pueden tardar
            max_retries=0,
        )
        # Usa el mismo modelo que el chat. Si el modelo no soporta visión,
        # las llamadas fallarán.
        self._model = settings.gemini_model or "gemini-3.5-flash-lite"

    def can_handle(self, mime_type: str) -> bool:
        return mime_type in SUPPORTED_MIMES

    async def extract_async(self, path: Path) -> list[ExtractedPage]:
        """Lee la imagen y la procesa con Gemini Vision."""
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ExtractionError(f"No se pudo leer la imagen: {exc}") from exc

        if len(data) > MAX_IMAGE_BYTES:
            raise ExtractionError(
                f"Imagen demasiado grande ({len(data) // 1024} KB). "
                f"Máximo: {MAX_IMAGE_BYTES // (1024 * 1024)} MB"
            )
        if len(data) == 0:
            raise ExtractionError("La imagen está vacía")

        # Detectar MIME real por la extensión.
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        if mime not in SUPPORTED_MIMES:
            mime = "image/png"

        # Codificar en base64 y construir data URL.
        b64 = base64.b64encode(data).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": EXTRACTION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=4_000,
            )
        except Exception as exc:
            log.warning(
                "image_extraction_llm_failed",
                path=str(path),
                error=str(exc)[:200],
            )
            raise ExtractionError(
                f"Gemini Vision falló al procesar la imagen: {exc}"
            ) from exc

        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise ExtractionError(
                "Gemini devolvió una respuesta vacía para la imagen"
            )

        return [
            ExtractedPage(
                text=text,
                meta={
                    "source": "image",
                    "mime_type": mime,
                    "size_bytes": len(data),
                    "model": self._model,
                },
            )
        ]

    # Método síncrono por compatibilidad con el protocolo DocumentExtractor.
    # No se usa en la práctica: el registry detecta `extract_async` y lo
    # llama directamente. Si alguien lo llama, lanzamos error claro.
    def extract(self, path: Path) -> list[ExtractedPage]:
        raise ExtractionError(
            "ImageExtractor es asíncrono. Usa extract_async()."
        )