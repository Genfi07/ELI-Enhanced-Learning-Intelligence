"""Endpoints de memoria del usuario.

Reglas:
  - Todos los endpoints requieren autenticación (`current_user`).
  - Todas las operaciones filtran por `user_id`. No existe forma de acceder
    a memorias de otro usuario, ni siquiera pasando un id ajeno (→ 404).
  - `DELETE` es soft-delete: la memoria pasa a DELETED y deja de aparecer
    en los listados. La fila se conserva para auditoría.
  - Las memorias se crean normalmente de forma automática (vía MemoryExtractor).
    Este endpoint de creación existe para casos de uso explícitos del usuario.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.core.schemas.memory import MemoryCandidate, MemoryEventOut, MemoryOut
from app.db.models.memory import MemoryEvent
from app.db.models.user import User
from app.llm.embeddings_router import build_embeddings_provider
from app.memory.store import MemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])


# --------------------------------------------------------------------------- #
# Schemas locales
# --------------------------------------------------------------------------- #
class MemoryCreate(BaseModel):
    type: str = Field(pattern="^(FACT|PREFERENCE|GOAL|INSTRUCTION|EPISODE)$")
    content: str = Field(min_length=3, max_length=2000)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=3, max_length=2000)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _store(session: AsyncSession) -> MemoryStore:
    return MemoryStore(session, build_embeddings_provider())


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[MemoryOut])
async def list_memories(
    status_filter: str | None = Query(default="ACTIVE", alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[MemoryOut]:
    store = _store(session)
    memories = await store.list_for_user(
        user.id, status=status_filter, type=type_filter
    )
    return [MemoryOut.from_model(m) for m in memories]


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(
    body: MemoryCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> MemoryOut:
    store = _store(session)
    candidate = MemoryCandidate(
        type=body.type,  # type: ignore[arg-type]
        content=body.content,
        importance=body.importance,
        confidence=body.confidence,
        source="EXPLICIT",
    )
    mem = await store.create_from_candidate(user.id, candidate)
    await session.commit()
    # Tras el commit, `mem` está expirado. Refrescamos para asegurarnos de que
    # todos los atributos (created_at, updated_at generados por la BD) están
    # cargados dentro del contexto async antes de serializar.
    await session.refresh(mem)
    return MemoryOut.from_model(mem)


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(
    memory_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> MemoryOut:
    store = _store(session)
    mem = await store.get(user.id, memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memoria no encontrada")
    return MemoryOut.from_model(mem)


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> MemoryOut:
    store = _store(session)
    mem = await store.update_content(
        user.id,
        memory_id,
        content=body.content,
        importance=body.importance,
        confidence=body.confidence,
        actor="USER",
    )
    if mem is None:
        raise HTTPException(status_code=404, detail="Memoria no encontrada")
    await session.commit()
    # Tras el UPDATE, SQLAlchemy expira `updated_at` (columna con onupdate
    # server-side) porque no conoce el valor que generó la BD. Recargarlo
    # explícitamente con refresh() lo hace dentro del contexto async, evitando
    # el MissingGreenlet al serializar la respuesta.
    await session.refresh(mem)
    return MemoryOut.from_model(mem)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> None:
    store = _store(session)
    ok = await store.soft_delete(user.id, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memoria no encontrada")
    await session.commit()


@router.get("/{memory_id}/history", response_model=list[MemoryEventOut])
async def get_memory_history(
    memory_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[MemoryEventOut]:
    # Verificamos propiedad antes de listar el historial
    store = _store(session)
    mem = await store.get(user.id, memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memoria no encontrada")

    stmt = (
        select(MemoryEvent)
        .where(MemoryEvent.memory_id == memory_id)
        .order_by(MemoryEvent.created_at.asc())
    )
    events = list((await session.scalars(stmt)).all())
    return [
        MemoryEventOut(
            id=e.id,
            memory_id=e.memory_id,
            event=e.event,
            previous_content=e.previous_content,
            reason=e.reason,
            actor=e.actor,
            created_at=e.created_at,
        )
        for e in events
    ]