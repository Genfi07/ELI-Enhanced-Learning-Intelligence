"""Pipeline de ingesta de documentos.

Flujo completo:
  1. Marcar documento como PROCESSING.
  2. Descargar bytes del StorageBackend.
  3. Escribir a archivo temporal (los extractores leen de Path).
  4. Extraer texto con el ExtractorRegistry.
  5. Chunkificar con DocumentChunker.
  6. Embedder los chunks en batch.
  7. Insertar chunks + actualizar contador.
  8. Marcar documento como READY.
  9. Borrar el temporal.

En cualquier fallo:
  - Marcar documento como FAILED con el mensaje de error.
  - Borrar el temporal.
  - No propagar la excepción (la task corre en background).

Diseño:
  - La task abre su PROPIA sesión de BD con session_scope(). La sesión del
    request del endpoint ya está cerrada cuando esto corre.
  - `schedule_ingest` respeta `settings.ingestion_enabled`: en tests se
    desactiva para evitar tareas de fondo compitiendo con la lógica de
    los tests.
"""
from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

from app.config.settings import get_settings
from app.core.contracts.embeddings import EmbeddingsProvider
from app.core.contracts.storage import StorageBackend
from app.db.session import session_scope
from app.observability.logging import get_logger
from app.rag.chunker import DocumentChunker
from app.rag.extractors.base import ExtractorRegistry, UnsupportedMimeType
from app.rag.store import KnowledgeStore

log = get_logger(__name__)


class IngestionError(RuntimeError):
    """Error durante la ingesta de un documento."""


class DocumentIngestor:
    def __init__(
        self,
        storage: StorageBackend,
        embeddings: EmbeddingsProvider,
        extractors: ExtractorRegistry | None = None,
        chunker: DocumentChunker | None = None,
    ) -> None:
        self.storage = storage
        self.embeddings = embeddings
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
        """Lanza la ingesta en background. No bloquea.

        Si `settings.ingestion_enabled=False` (típicamente en tests), no hace
        nada. El documento queda en PENDING y los tests pueden verificarlo
        sin race conditions.
        """
        if not get_settings().ingestion_enabled:
            return
        asyncio.create_task(self._run(document_id, user_id))

    async def ingest_sync(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Igual que schedule_ingest pero bloquea hasta terminar.

        Útil para tests y para procesamiento batch. Ignora el flag
        `ingestion_enabled`: si lo llamas explícitamente, corre.
        """
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

            # 4. Embeddings en batch
            texts = [c.text for c in chunks]
            vectors = await self.embeddings.embed_batch(texts)
            if len(vectors) != len(texts):
                raise IngestionError(
                    f"embeddings devolvió {len(vectors)} vectores para {len(texts)} chunks"
                )

            # 5. Persistir chunks + actualizar documento (nueva sesión)
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
    # Helpers
    # ------------------------------------------------------------------ #
    async def _write_tempfile(self, data: bytes, storage_path: str) -> Path:
        """Escribe `data` a un archivo temporal preservando la extensión."""
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


def _build_registry() -> ExtractorRegistry:
    from app.rag.extractors.base import build_default_registry
    return build_default_registry()