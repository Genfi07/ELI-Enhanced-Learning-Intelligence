"""Tests del MemoryConsolidator.

Dos niveles:
  1. `decide()` — función pura, exhaustivamente testeada con casos fabricados.
  2. `MemoryConsolidator.consolidate()` — con store real (FakeEmbeddings) para
     probar CREATE e IGNORE end-to-end. SUPERSEDE se prueba en `decide()`.

Con FakeEmbeddings las similitudes entre textos distintos son esencialmente
aleatorias, así que los tests de integración solo cubren:
  - CREATE (sin vecinos)
  - IGNORE (mismo texto exacto → vector idéntico → similitud 1.0)
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas.memory import MemoryCandidate
from app.db.models.user import User
from app.llm.embeddings_fake import FakeEmbeddingsProvider
from app.memory.consolidator import (
    MemoryConsolidator,
    decide,
)
from app.memory.store import MemoryStore, ScoredMemory
from tests.conftest import ROLE_USER_ID


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class FakeMemory:
    """Sustituto ligero para los tests de `decide()`."""

    def __init__(self, mid=None, mtype="FACT", content="something"):
        self.id = mid or uuid.uuid4()
        self.type = mtype
        self.content = content


def _neighbor(sim: float, mtype: str = "FACT") -> ScoredMemory:
    """Crea un vecino con la similitud indicada. score y similarity van juntos
    en tests puros: así queda explícito que decide() mira `similarity`."""
    return ScoredMemory(
        memory=FakeMemory(mtype=mtype),  # type: ignore[arg-type]
        score=sim,
        similarity=sim,
    )


# --------------------------------------------------------------------------- #
# decide() — pura
# --------------------------------------------------------------------------- #
def test_decide_creates_when_no_neighbors():
    cand = MemoryCandidate(type="FACT", content="El usuario vive en Madrid")
    d = decide(cand, [])
    assert d.action == "CREATE"


def test_decide_ignores_exact_duplicate():
    cand = MemoryCandidate(type="FACT", content="El usuario vive en Madrid")
    d = decide(cand, [_neighbor(0.99)])
    assert d.action == "IGNORE"
    assert d.target_memory_id is not None


def test_decide_supersedes_close_match():
    cand = MemoryCandidate(type="FACT", content="El usuario vive en Barcelona")
    d = decide(cand, [_neighbor(0.88)])
    assert d.action == "SUPERSEDE"
    assert d.target_memory_id is not None


def test_decide_creates_when_similarity_below_threshold():
    cand = MemoryCandidate(type="FACT", content="El usuario vive en Madrid")
    d = decide(cand, [_neighbor(0.75)])
    assert d.action == "CREATE"


def test_decide_uses_highest_similarity():
    """Si hay varios vecinos, se decide por el de mayor similitud."""
    cand = MemoryCandidate(type="FACT", content="contenido de prueba")
    d = decide(cand, [_neighbor(0.5), _neighbor(0.98), _neighbor(0.7)])
    assert d.action == "IGNORE"  # el 0.98 gana


def test_decide_custom_thresholds():
    cand = MemoryCandidate(type="FACT", content="contenido de prueba")
    d = decide(
        cand,
        [_neighbor(0.80)],
        duplicate_threshold=0.99,
        supersede_threshold=0.70,
    )
    assert d.action == "SUPERSEDE"


# --------------------------------------------------------------------------- #
# consolidate() — integración con store real
# --------------------------------------------------------------------------- #
@pytest.fixture
async def memory_user(session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        name="Memory User",
        email=f"mem-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


@pytest.mark.asyncio
async def test_consolidate_creates_new_memory(
    session: AsyncSession, memory_user: User
):
    store = MemoryStore(session, FakeEmbeddingsProvider())
    cons = MemoryConsolidator(store)
    cands = [
        MemoryCandidate(
            type="FACT", content="El usuario trabaja en finanzas",
            importance=0.7, confidence=0.9,
        )
    ]
    results = await cons.consolidate(memory_user.id, cands)
    await session.commit()

    assert len(results) == 1
    assert results[0].action == "CREATE"
    assert results[0].memory.content == "El usuario trabaja en finanzas"


@pytest.mark.asyncio
async def test_consolidate_ignores_exact_duplicate(
    session: AsyncSession, memory_user: User
):
    """Con FakeEmbeddings, mismo texto → mismo vector → similitud 1.0 → IGNORE."""
    store = MemoryStore(session, FakeEmbeddingsProvider())
    cons = MemoryConsolidator(store)

    cand = MemoryCandidate(
        type="PREFERENCE", content="Prefiere explicaciones paso a paso",
        importance=0.9, confidence=0.9,
    )
    r1 = await cons.consolidate(memory_user.id, [cand])
    await session.commit()
    assert r1[0].action == "CREATE"
    first_id = r1[0].memory.id

    # Mismo contenido exacto
    r2 = await cons.consolidate(memory_user.id, [cand])
    await session.commit()
    assert r2[0].action == "IGNORE"
    assert r2[0].memory.id == first_id

    # Verificar que no hay dos memorias ACTIVE con ese contenido
    active = await store.list_for_user(memory_user.id, status="ACTIVE")
    matching = [m for m in active if m.content == cand.content]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_consolidate_multiple_candidates(
    session: AsyncSession, memory_user: User
):
    store = MemoryStore(session, FakeEmbeddingsProvider())
    cons = MemoryConsolidator(store)
    cands = [
        MemoryCandidate(
            type="FACT", content="El usuario vive en Madrid",
            importance=0.7, confidence=0.9,
        ),
        MemoryCandidate(
            type="GOAL", content="Está aprendiendo Rust",
            importance=0.6, confidence=0.85,
        ),
    ]
    results = await cons.consolidate(memory_user.id, cands)
    await session.commit()

    assert len(results) == 2
    assert all(r.action == "CREATE" for r in results)


@pytest.mark.asyncio
async def test_consolidate_respects_type(
    session: AsyncSession, memory_user: User
):
    """Un FACT no debe verse afectado por una PREFERENCE con contenido similar."""
    store = MemoryStore(session, FakeEmbeddingsProvider())
    cons = MemoryConsolidator(store)

    # Creamos una PREFERENCE
    await cons.consolidate(
        memory_user.id,
        [MemoryCandidate(
            type="PREFERENCE", content="Prefiere explicaciones paso a paso",
            importance=0.9, confidence=0.9,
        )],
    )
    await session.commit()

    # Llega un FACT con el mismo contenido exacto (raro pero probémoslo)
    r = await cons.consolidate(
        memory_user.id,
        [MemoryCandidate(
            type="FACT", content="Prefiere explicaciones paso a paso",
            importance=0.7, confidence=0.9,
        )],
    )
    await session.commit()

    # Distinto tipo → no se considera duplicado → CREATE
    assert r[0].action == "CREATE"