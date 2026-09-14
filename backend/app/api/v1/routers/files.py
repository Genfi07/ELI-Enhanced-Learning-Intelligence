"""Endpoints de gestión de archivos / documentos.

Diseño:
  - POST /files sube un archivo, lo persiste en storage, crea el registro en
    BD y encola la ingesta async. Devuelve 202 Accepted con el documento en
    estado PENDING. El cliente consulta GET /files/{id} para ver el progreso.
  - Todos los endpoints requieren autenticación y filtran por user_id.
  - Límite de tamaño configurable (settings.max_upload_size_mb).
  - DELETE borra el registro + el archivo físico + los chunks (cascade).
  - POST /files/{id}/reprocess reintenta la ingesta si falló.

Lista de MIME types aceptados: se delega al ExtractorRegistry. Si no hay
extractor para el MIME, se devuelve 415 Unsupported Media Type.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.config.settings import get_settings
from app.core.schemas.document import DocumentOut
from app.db.models.user import User
from app.llm.embeddings_router import build_embeddings_provider
from app.observability.logging import get_logger
from app.rag.extractors.base import build_default_registry
from app.rag.ingest import DocumentIngestor
from app.rag.store import KnowledgeStore
from app.storage.local import LocalStorageBackend

log = get_logger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


# --------------------------------------------------------------------------- #
# Singletons (stateless, se pueden reusar entre requests)
# --------------------------------------------------------------------------- #
_storage = LocalStorageBackend()
_embeddings = build_embeddings_provider()
_extractors = build_default_registry()
_ingestor = DocumentIngestor(
    storage=_storage,
    embeddings=_embeddings,
    extractors=_extractors,
)


def _store(session: AsyncSession) -> KnowledgeStore:
    return KnowledgeStore(session, _embeddings)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DocumentOut:
    settings = get_settings()

    # 1. Validar MIME
    mime_type = (file.content_type or "application/octet-stream").strip()
    if _extractors.find(mime_type) is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de archivo no soportado: {mime_type}",
        )

    # 2. Validar tamaño (leemos una vez, no dos)
    data = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo excede {settings.max_upload_size_mb} MB",
        )
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    # 3. Guardar en storage
    original_name = file.filename or "archivo"
    try:
        storage_path = await _storage.save(user.id, original_name, data)
    except Exception as exc:
        log.exception("file_storage_save_failed", error=str(exc))
        raise HTTPException(
            status_code=500, detail="No se pudo guardar el archivo"
        ) from exc

    # 4. Crear registro en BD
    store = _store(session)
    doc = await store.create_document(
        user.id,
        title=original_name[:300],
        mime_type=mime_type,
        size_bytes=len(data),
        storage_path=storage_path,
        source_type="UPLOAD",
        meta={"original_filename": original_name},
    )
    await session.commit()
    await session.refresh(doc)

    # 5. Encolar ingesta async (no bloquea la respuesta)
    _ingestor.schedule_ingest(doc.id, user.id)

    return DocumentOut.from_model(doc)


@router.get("", response_model=list[DocumentOut])
async def list_files(
    status_filter: str | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[DocumentOut]:
    store = _store(session)
    docs = await store.list_documents(user.id, status=status_filter)
    return [DocumentOut.from_model(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_file(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DocumentOut:
    store = _store(session)
    doc = await store.get_document(user.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return DocumentOut.from_model(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_file(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> None:
    store = _store(session)
    doc = await store.get_document(user.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    storage_path = doc.storage_path
    await store.delete_document(user.id, document_id)
    await session.commit()

    # Borrado del archivo físico (después del commit, para no perder consistencia
    # si el borrado en BD falla). Si falla el borrado físico, se loggea pero no
    # se rompe el request: el documento ya no existe para el usuario.
    try:
        await _storage.delete(user.id, storage_path)
    except Exception as exc:
        log.warning(
            "file_storage_delete_failed",
            document_id=str(document_id),
            error=str(exc),
        )


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_file(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DocumentOut:
    """Reintenta la ingesta de un documento.

    Útil cuando falló por un error transitorio (timeout de embeddings, etc.).
    Borra los chunks previos (si los hubiera) y relanza el pipeline.
    """
    store = _store(session)
    doc = await store.get_document(user.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if doc.status == "PROCESSING":
        raise HTTPException(
            status_code=409, detail="El documento ya está siendo procesado"
        )

    # Limpiar chunks previos y resetear estado
    await store.delete_chunks_for_document(document_id)
    await store.update_status(document_id, "PENDING", chunk_count=0)
    await session.commit()
    await session.refresh(doc)

    _ingestor.schedule_ingest(doc.id, user.id)
    return DocumentOut.from_model(doc)