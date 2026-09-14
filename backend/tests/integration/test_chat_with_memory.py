"""Test end-to-end del chat con memoria inyectada.

Verifica el pipeline completo:
  1. Cliente envía mensaje.
  2. Orquestador recupera memorias relacionadas del usuario.
  3. Inyecta el bloque <memory> en el contexto.
  4. Marca las memorias como usadas.
  5. Emite memory_used en el evento final.

Para testear sin depender del LLM real, este test:
  - Desactiva la extracción async (conftest ya lo hace).
  - Inserta memorias directamente en BD antes de chatear.
  - Verifica el evento `final` del SSE.

Regla de oro con SQLAlchemy async + expire_all:
  Captura siempre los IDs como valores planos (uuid.UUID) ANTES de llamar a
  `expire_all()`. Acceder a un atributo de un objeto ORM expirado dispara IO
  fuera del contexto greenlet → MissingGreenlet.

Nota sobre el DecisionEngine (Fase 3):
  Los mensajes de los tests usan palabras que están en `_MEMORY_MARKERS`
  ("como te dije", "prefiero", "trabajo con") para forzar la ruta STANDARD
  y activar la recuperación de memoria. En Fase 4 el clasificador pasará a
  usar embeddings y reconocerá más variantes ("recuérdame", "acuérdate", etc.).
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas.memory import MemoryCandidate
from app.db.models.user import User
from app.llm.embeddings_fake import FakeEmbeddingsProvider
from app.memory.store import MemoryStore
from tests.conftest import ROLE_USER_ID


async def _read_sse(response) -> list[dict]:
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.fixture
async def mem_user(session: AsyncSession) -> User:
    """Usuario limpio para este test."""
    u = User(
        id=uuid.uuid4(),
        name="Chat Memory User",
        email=f"chat-mem-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


async def _seed_memory(
    session: AsyncSession, user_id: uuid.UUID, content: str
) -> None:
    """Inserta una memoria para el usuario. Simula lo que haría el extractor."""
    store = MemoryStore(session, FakeEmbeddingsProvider())
    await store.create_from_candidate(
        user_id,
        MemoryCandidate(
            type="PREFERENCE",
            content=content,
            importance=0.9,
            confidence=0.9,
            source="EXPLICIT",
        ),
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_chat_without_memory(client, mem_user: User):
    """Sin memorias, memory_used debe ser 0."""
    uid = mem_user.id
    headers = {"X-Dev-User-Id": str(uid)}

    r = await client.post(
        "/api/v1/conversations", json={"title": "sin memoria"}, headers=headers
    )
    conv_id = r.json()["id"]

    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Como te dije antes, prefiero explicaciones paso a paso",
        },
        headers=headers,
    )
    assert r.status_code == 200
    events = await _read_sse(r)
    final = events[-1]
    assert final["type"] == "final"
    # La ruta debe ser STANDARD o DEEP, no FAST (contiene "como te dije")
    assert final["route"] in ("STANDARD", "DEEP")
    assert final["memory_used"] == 0


@pytest.mark.asyncio
async def test_chat_retrieves_relevant_memory(
    client, mem_user: User, session: AsyncSession
):
    """Con memoria relacionada, memory_used debe ser >= 1."""
    uid = mem_user.id

    await _seed_memory(
        session,
        uid,
        "Prefiere explicaciones paso a paso con ejemplos concretos",
    )

    headers = {"X-Dev-User-Id": str(uid)}

    r = await client.post(
        "/api/v1/conversations", json={"title": "con memoria"}, headers=headers
    )
    conv_id = r.json()["id"]

    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Prefiero explicaciones paso a paso por favor",
        },
        headers=headers,
    )
    assert r.status_code == 200
    events = await _read_sse(r)
    final = events[-1]
    assert final["type"] == "final"
    assert final["route"] in ("STANDARD", "DEEP")
    assert final["memory_used"] >= 1, (
        f"Esperaba memory_used>=1, llegó {final['memory_used']}"
    )


@pytest.mark.asyncio
async def test_chat_marks_memory_as_used(
    client, mem_user: User, session: AsyncSession
):
    """Tras un turno que usa memoria, usage_count se incrementa."""
    # Capturamos el UUID como valor plano ANTES de cualquier expire_all().
    # Los valores uuid.UUID no son objetos ORM: accederlos nunca dispara IO.
    uid = mem_user.id

    await _seed_memory(
        session, uid, "El usuario trabaja en finanzas y análisis de datos"
    )

    headers = {"X-Dev-User-Id": str(uid)}
    r = await client.post(
        "/api/v1/conversations", json={"title": "uso de memoria"}, headers=headers
    )
    conv_id = r.json()["id"]

    # Estado inicial
    store = MemoryStore(session, FakeEmbeddingsProvider())
    before = await store.list_for_user(uid, status="ACTIVE")
    assert len(before) == 1
    assert before[0].usage_count == 0

    # Chateamos con palabras que activan needs_memory ("como te dije",
    # "trabajo con") y que además matchean por keyword con la memoria
    # sembrada ("finanzas", "datos").
    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Como te dije, trabajo con finanzas y datos",
        },
        headers=headers,
    )
    await _read_sse(r)  # consumimos el stream

    # Refrescamos desde BD. El orquestador abrió su propia sesión y actualizó
    # el registro; expire_all() invalida la caché de esta sesión de test, así
    # que la siguiente query recargará los objetos Memory actualizados.
    session.expire_all()
    after = await store.list_for_user(uid, status="ACTIVE")
    assert len(after) == 1
    assert after[0].usage_count == 1
    assert after[0].last_used_at is not None


@pytest.mark.asyncio
async def test_chat_isolates_memories_between_users(
    client, session: AsyncSession
):
    """La memoria de A nunca aparece en el contexto de B."""
    # Creamos dos usuarios
    user_a = User(
        id=uuid.uuid4(),
        name="A",
        email=f"a-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    user_b = User(
        id=uuid.uuid4(),
        name="B",
        email=f"b-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add_all([user_a, user_b])
    await session.commit()

    # Capturamos ambos IDs como valores planos antes de cualquier expire.
    uid_a = user_a.id
    uid_b = user_b.id

    # A tiene una memoria, B no
    await _seed_memory(
        session, uid_a, "Prefiere explicaciones paso a paso extensas"
    )

    # Conversación de B
    headers_b = {"X-Dev-User-Id": str(uid_b)}
    r = await client.post(
        "/api/v1/conversations", json={"title": "de B"}, headers=headers_b
    )
    conv_id = r.json()["id"]

    # B pregunta con las mismas keywords que la memoria de A
    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Prefiero explicaciones paso a paso",
        },
        headers=headers_b,
    )
    events = await _read_sse(r)
    final = events[-1]

    # B no debe haber usado ninguna memoria (la de A está aislada)
    assert final["memory_used"] == 0