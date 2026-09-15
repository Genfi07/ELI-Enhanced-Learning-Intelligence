"""Endpoints de gestión de archivos / documentos.

Ciclo de vida efímero:
  - POST /files: sube archivo, persiste en storage, encola ingesta.
  - Tras la ingesta: el archivo físico se BORRA. Solo quedan chunks + resumen.
  - DELETE /files/{id}: soft-delete. Marca deleted_at, borra chunks.
    El documento sigue visible en la lista pero tachado en rojo.
  - POST /files/{id}/hide: oculta la entrada de la lista del usuario.
    ELI sigue sabiendo que existió (summary + topics).
  - GET /files?state=active|deleted|all: filtro por estado visible.

Estados visibles en UI (derivados):
  - active:  deleted_at IS NULL AND hidden_at IS NULL
  - deleted: deleted_at IS NOT NULL AND hidden_at IS NULL
  - all:     hidden_at IS NULL (incluye active + deleted)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.config.settings import get_settings
from app.core.schemas.document import DocumentOut
from app.db.models.user import User
from app.llm.embeddings_router import build_embeddings_provider
from app.llm.router import build_provider
from app.observability.logging import get_logger
from app.rag.extractors.base import build_default_registry
from app.rag.ingest import DocumentIngestor
from app.rag.store import KnowledgeStore
from app.storage.local import LocalStorageBackend

log = get_logger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


_storage = LocalStorageBackend()
_embeddings = build_embeddings_provider()
_llm = build_provider()
_extractors = build_default_registry()
_ingestor = DocumentIngestor(
    storage=_storage,
    embeddings=_embeddings,
    llm=_llm,
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

    mime_type = (file.content_type or "application/octet-stream").strip()
    if _extractors.find(mime_type) is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de archivo no soportado: {mime_type}",
        )

    data = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo excede {settings.max_upload_size_mb} MB",
        )
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    original_name = file.filename or "archivo"
    try:
        storage_path = await _storage.save(user.id, original_name, data)
    except Exception as exc:
        log.exception("file_storage_save_failed", error=str(exc))
        raise HTTPException(
            status_code=500, detail="No se pudo guardar el archivo"
        ) from exc

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

    _ingestor.schedule_ingest(doc.id, user.id)
    return DocumentOut.from_model(doc)


@router.get("", response_model=list[DocumentOut])
async def list_files(
    state: str = Query(
        default="active",
        pattern="^(active|deleted|all)$",
        description="Filtro de visibilidad: active, deleted, all",
    ),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[DocumentOut]:
    """Lista documentos según el estado visible.

    - active:  no eliminados, no ocultos.
    - deleted: eliminados pero no ocultos.
    - all:     todos los no ocultos.
    """
    store = _store(session)
    docs = await store.list_documents_by_state(user.id, state=state)
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


@router.delete("/{document_id}", response_model=DocumentOut)
async def delete_file(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DocumentOut:
    """Soft-delete: marca deleted_at y borra chunks + embeddings.

    El documento sigue visible en la lista (tachado en rojo) hasta que el
    usuario llame a POST /files/{id}/hide.
    """
    store = _store(session)
    doc = await store.get_document(user.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if doc.deleted_at is not None:
        raise HTTPException(
            status_code=409, detail="El documento ya fue eliminado"
        )

    doc = await store.soft_delete_document(user.id, document_id)
    await session.commit()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    await session.refresh(doc)
    return DocumentOut.from_model(doc)


@router.post("/{document_id}/hide", response_model=DocumentOut)
async def hide_file(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DocumentOut:
    """Oculta la entrada del documento en la lista del usuario.

    A partir de aquí, el documento no aparece en ninguna consulta normal.
    ELI sigue sabiendo que existió (summary + topics quedan en BD).

    Solo se puede ocultar si el documento ya fue eliminado (deleted_at).
    """
    store = _store(session)
    doc = await store.get_document(user.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if doc.deleted_at is None:
        raise HTTPException(
            status_code=409,
            detail="Solo se pueden ocultar documentos previamente eliminados",
        )

    doc = await store.hide_document(user.id, document_id)
    await session.commit()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    await session.refresh(doc)
    return DocumentOut.from_model(doc)


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
    """Reintenta la ingesta si el documento está en estado FAILED.

    Requiere que el archivo físico todavía exista. Solo está disponible
    cuando la ingesta falló (porque si tuvo éxito, el archivo se borra).
    """
    store = _store(session)
    doc = await store.get_document(user.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if doc.status == "PROCESSING":
        raise HTTPException(
            status_code=409, detail="El documento ya está siendo procesado"
        )
    if doc.status == "READY":
        raise HTTPException(
            status_code=409,
            detail="El documento ya fue procesado y su archivo físico fue borrado",
        )
    if doc.deleted_at is not None:
        raise HTTPException(
            status_code=409, detail="El documento está eliminado"
        )

    # Verificar que el archivo físico sigue existiendo.
    try:
        still_exists = await _storage.exists(user.id, doc.storage_path)
    except Exception:
        still_exists = False
    if not still_exists:
        raise HTTPException(
            status_code=410,
            detail="El archivo físico ya no existe. Vuelve a subirlo.",
        )

    await store.delete_chunks_for_document(document_id)
    await store.update_status(document_id, "PENDING", chunk_count=0)
    await session.commit()
    await session.refresh(doc)

    _ingestor.schedule_ingest(doc.id, user.id)
    return DocumentOut.from_model(doc)