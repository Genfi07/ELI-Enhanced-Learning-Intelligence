"""Pipeline de ingesta de documentos con ciclo de vida efímero.

Flujo completo:
  1. Marcar documento como PROCESSING.
  2. Descargar bytes del StorageBackend.
  3. Escribir a archivo temporal (los extractores leen de Path).
  4. Extraer texto con el ExtractorRegistry.
  5. Chunkificar con DocumentChunker.
  6. Embedder los chunks EN LOTES PEQUEÑOS (respeta rate limits).
  7. Insertar chunks + actualizar contador → READY.
  8. Generar summary + topics con LLM.
  9. Borrar el archivo físico (archivo original ya no se guarda).
 10. Borrar el temporal.

En cualquier fallo:
  - Marcar documento como FAILED.
  - Borrar el temporal.
  - NO borrar el archivo físico (así el usuario puede reprocesar).
"""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import get_settings
from app.core.contracts.embeddings import EmbeddingsProvider
from app.core.contracts.llm import LLMProvider
from app.core.contracts.storage import StorageBackend
from app.core.schemas.llm import LLMMessage
from app.db.session import session_scope
from app.observability.logging import get_logger
from app.rag.chunker import DocumentChunker
from app.rag.extractors.base import ExtractorRegistry, UnsupportedMimeType
from app.rag.store import KnowledgeStore

log = get_logger(__name__)


class IngestionError(RuntimeError):
    """Error durante la ingesta de un documento."""


# Máximo de caracteres del documento que enviamos al LLM para resumir.
SUMMARY_INPUT_MAX_CHARS = 12_000

# Configuración del batching de embeddings.
# Con free tier de Gemini (~15 RPM) y Voyage (~3 RPM), archivos grandes
# revientan si se mandan muchos chunks juntos. Lotes de 10 con pausa
# de 3.5s y retry exponencial evitan los 429 consecutivos.
EMBED_BATCH_SIZE = 10
EMBED_BATCH_DELAY_SECONDS = 3.5
EMBED_MAX_RETRIES = 5
EMBED_RETRY_BASE_DELAY = 2.0  # 2s, 4s, 8s, 16s, 32s


SUMMARY_PROMPT = """\
Eres un extractor de resúmenes y temas para ELI, una asistente con memoria.

Recibes el texto de un documento subido por el usuario. Tu trabajo es
producir un resumen corto y una lista de topics para que ELI pueda
recordar de qué iba el documento incluso después de que el usuario
lo elimine (solo se conserva este resumen).

Devuelve EXCLUSIVAMENTE un JSON con este formato. Sin markdown ni
explicaciones adicionales:

{
  "summary": "resumen de 2-3 frases claras sobre qué trata el documento",
  "topics": ["topic1", "topic2", "topic3"]
}

Reglas:
- summary: 2-3 frases. Describe el contenido, no lo valores.
- topics: entre 3 y 8 temas concretos. Palabras o frases cortas.
- Si el documento es basura o no tiene contenido útil, devuelve
  {"summary": null, "topics": []}.
"""


class DocumentIngestor:
    def __init__(
        self,
        storage: StorageBackend,
        embeddings: EmbeddingsProvider,
        llm: LLMProvider | None = None,
        extractors: ExtractorRegistry | None = None,
        chunker: DocumentChunker | None = None,
    ) -> None:
        self.storage = storage
        self.embeddings = embeddings
        self.llm = llm
        self.extractors = extractors or _build_registry()
        self.chunker = chunker or DocumentChunker()

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def schedule_ingest(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Lanza la ingesta en background. No bloquea."""
        if not get_settings().ingestion_enabled:
            return
        task = asyncio.create_task(self._run(document_id, user_id))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    async def ingest_sync(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Igual que schedule_ingest pero bloquea hasta terminar."""
        await self._run(document_id, user_id)

    # ------------------------------------------------------------------ #
    # Pipeline
    # ------------------------------------------------------------------ #
    async def _run(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        tmp_path: Path | None = None
        try:
            async with session_scope() as session:
                store = KnowledgeStore(session, self.embeddings)

                doc = await store.get_document(user_id, document_id)
                if doc is None:
                    log.warning(
                        "ingest_document_not_found",
                        document_id=str(document_id),
                        user_id=str(user_id),
                    )
                    return

                await store.update_status(document_id, "PROCESSING")
                storage_path = doc.storage_path
                mime_type = doc.mime_type
                title = doc.title

            log.info(
                "ingest_started",
                document_id=str(document_id),
                mime=mime_type,
                title=title,
            )

            # 1. Descargar bytes y escribirlos a temporal
            data = await self.storage.load(user_id, storage_path)
            tmp_path = await self._write_tempfile(data, storage_path)

            # 2. Extraer texto
            try:
                pages = await self.extractors.extract_async(tmp_path, mime_type)
            except UnsupportedMimeType as exc:
                raise IngestionError(str(exc)) from exc

            if not pages:
                raise IngestionError(
                    "no se pudo extraer texto del documento (¿imagen sin OCR?)"
                )

            # 3. Chunkificar
            chunks = self.chunker.chunk_pages(pages)
            if not chunks:
                raise IngestionError("el documento no produjo chunks")

            # 4. Embeddings EN LOTES para respetar rate limits.
            texts = [c.text for c in chunks]
            vectors = await self._embed_in_batches(texts, document_id)

            if len(vectors) != len(texts):
                raise IngestionError(
                    f"embeddings devolvió {len(vectors)} vectores para {len(texts)} chunks"
                )

            # 5. Persistir chunks + READY
            async with session_scope() as session:
                store = KnowledgeStore(session, self.embeddings)
                await store.insert_chunks(
                    document_id,
                    [
                        {
                            "chunk_index": c.chunk_index,
                            "content": c.text,
                            "token_count": c.token_count,
                            "meta": c.meta,
                            "embedding": vec,
                        }
                        for c, vec in zip(chunks, vectors, strict=True)
                    ],
                )
                await store.update_status(
                    document_id, "READY", chunk_count=len(chunks)
                )

            log.info(
                "ingest_done",
                document_id=str(document_id),
                chunks=len(chunks),
                chars=sum(len(c.text) for c in chunks),
            )

            # 6. Summary + topics con LLM
            await self._generate_summary_and_topics(
                document_id, chunks_text=texts
            )

            # 7. Borrar el archivo físico (ya no lo necesitamos)
            try:
                await self.storage.delete(user_id, storage_path)
                async with session_scope() as session:
                    store = KnowledgeStore(session, self.embeddings)
                    await store.mark_physical_deleted(document_id)
                log.info(
                    "ingest_physical_file_removed",
                    document_id=str(document_id),
                )
            except Exception as exc:
                log.warning(
                    "ingest_physical_delete_failed",
                    document_id=str(document_id),
                    error=str(exc),
                )
        except Exception as exc:
            log.warning(
                "ingest_failed",
                document_id=str(document_id),
                error=str(exc),
            )
            try:
                async with session_scope() as session:
                    store = KnowledgeStore(session, self.embeddings)
                    await store.update_status(
                        document_id, "FAILED", error=str(exc)
                    )
            except Exception as inner:
                log.exception(
                    "ingest_failed_to_mark_failed",
                    document_id=str(document_id),
                    error=str(inner),
                )
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    # ------------------------------------------------------------------ #
    # Embeddings en lotes
    # ------------------------------------------------------------------ #
    async def _embed_in_batches(
        self,
        texts: list[str],
        document_id: uuid.UUID,
    ) -> list[list[float]]:
        """Embeddea en lotes pequeños con retry exponencial.

        Motivo: enviar 100+ chunks en una sola llamada revienta el rate
        limit de los proveedores free tier (Gemini ~15 RPM, Voyage ~3 RPM)
        y todo el pipeline falla con 429.
        """
        vectors: list[list[float]] = []
        total = len(texts)
        total_batches = (total + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

        for i in range(0, total, EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            batch_num = (i // EMBED_BATCH_SIZE) + 1

            # Retry con backoff exponencial por lote
            for attempt in range(EMBED_MAX_RETRIES):
                try:
                    batch_vectors = await self.embeddings.embed_batch(batch)
                    if len(batch_vectors) != len(batch):
                        raise IngestionError(
                            f"embeddings devolvió {len(batch_vectors)} vectores "
                            f"para {len(batch)} chunks en lote {batch_num}"
                        )
                    vectors.extend(batch_vectors)
                    log.info(
                        "ingest_embed_batch_ok",
                        document_id=str(document_id),
                        batch=batch_num,
                        total=total_batches,
                        size=len(batch),
                    )
                    break
                except Exception as exc:
                    if attempt == EMBED_MAX_RETRIES - 1:
                        raise IngestionError(
                            f"embeddings falló tras {EMBED_MAX_RETRIES} intentos "
                            f"en lote {batch_num}/{total_batches}: {str(exc)[:200]}"
                        ) from exc
                    # Backoff: 2s, 4s, 8s, 16s, 32s
                    wait = (2 ** attempt) * EMBED_RETRY_BASE_DELAY
                    log.warning(
                        "ingest_embed_retry",
                        document_id=str(document_id),
                        batch=batch_num,
                        attempt=attempt + 1,
                        wait_seconds=wait,
                        error=str(exc)[:200],
                    )
                    await asyncio.sleep(wait)

            # Pausa entre lotes (no después del último)
            if i + EMBED_BATCH_SIZE < total:
                await asyncio.sleep(EMBED_BATCH_DELAY_SECONDS)

        return vectors

    # ------------------------------------------------------------------ #
    # Summary + topics
    # ------------------------------------------------------------------ #
    async def _generate_summary_and_topics(
        self,
        document_id: uuid.UUID,
        *,
        chunks_text: list[str],
    ) -> None:
        if self.llm is None:
            return
        combined = "\n\n".join(chunks_text)[:SUMMARY_INPUT_MAX_CHARS]
        try:
            response = await self.llm.generate(
                [
                    LLMMessage(role="system", content=SUMMARY_PROMPT),
                    LLMMessage(role="user", content=combined),
                ],
                temperature=0.2,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            parsed = _extract_json(response.text or "")
            if parsed is None:
                return
            summary = parsed.get("summary")
            topics = parsed.get("topics") or []
            if not isinstance(topics, list):
                topics = []
            topics = [str(t)[:60] for t in topics[:10]]

            async with session_scope() as session:
                store = KnowledgeStore(session, self.embeddings)
                await store.update_summary_and_topics(
                    document_id,
                    summary=summary if isinstance(summary, str) else None,
                    topics=topics,
                )
        except Exception as exc:
            log.warning(
                "ingest_summary_failed",
                document_id=str(document_id),
                error=str(exc),
            )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _write_tempfile(self, data: bytes, storage_path: str) -> Path:
        ext = Path(storage_path).suffix or ".bin"

        def _write() -> Path:
            f = tempfile.NamedTemporaryFile(
                mode="wb", suffix=ext, delete=False, prefix="eli-ingest-"
            )
            try:
                f.write(data)
            finally:
                f.close()
            return Path(f.name)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _write)


# Tareas de fondo que deben sobrevivir al GC.
_background_tasks: set[asyncio.Task] = set()


def _build_registry() -> ExtractorRegistry:
    from app.rag.extractors.base import build_default_registry
    return build_default_registry()


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None