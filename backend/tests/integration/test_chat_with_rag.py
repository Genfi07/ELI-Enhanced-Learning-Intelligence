"""Test end-to-end de RAG en el chat.

Estrategia: sembrar documento + chunks directamente en BD (no dependemos
de la ingesta async, que corre en background y es difícil de sincronizar
en tests). Así verificamos la recuperación real del KnowledgeStore durante
un turno del orquestador.

Mensajes que activan `needs_rag=True` según el DecisionEngine contienen uno
de: "según", "documento", "pdf", "archivo", "apuntes", "manual", "paper",
"artículo".
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.llm.embeddings_fake import FakeEmbeddingsProvider
from app.rag.store import KnowledgeStore
from tests.conftest import ROLE_USER_ID


async def _read_sse(response) -> list[dict]:
    events: list[dict] = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.fixture
async def rag_user(session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        name="RAG User",
        email=f"rag-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


async def _seed_document(
    session: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    chunks: list[str],
) -> uuid.UUID:
    """Crea un Document READY con chunks reales y embeddings fake."""
    store = KnowledgeStore(session, FakeEmbeddingsProvider())
    doc = await store.create_document(
        user_id,
        title=title,
        mime_type="text/plain",
        size_bytes=sum(len(c) for c in chunks),
        storage_path=f"documents/{uuid.uuid4()}/original.txt",
    )
    await session.flush()

    emb = FakeEmbeddingsProvider()
    vectors = await emb.embed_batch(chunks)

    await store.insert_chunks(
        doc.id,
        [
            {
                "chunk_index": i,
                "content": text,
                "token_count": max(1, len(text) // 4),
                "meta": {"chunk": i},
                "embedding": vec,
            }
            for i, (text, vec) in enumerate(zip(chunks, vectors, strict=True))
        ],
    )
    await store.update_status(doc.id, "READY", chunk_count=len(chunks))
    await session.commit()
    return doc.id


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_chat_without_documents_has_zero_rag(client, rag_user: User):
    """Sin documentos, rag_used debe ser 0."""
    uid = rag_user.id
    headers = {"X-Dev-User-Id": str(uid)}

    r = await client.post(
        "/api/v1/conversations", json={"title": "sin docs"}, headers=headers
    )
    conv_id = r.json()["id"]

    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Según el documento que subí, resume los puntos clave",
        },
        headers=headers,
    )
    assert r.status_code == 200
    events = await _read_sse(r)
    final = events[-1]
    assert final["type"] == "final"
    assert final["route"] in ("STANDARD", "DEEP")
    assert final["rag_used"] == 0


@pytest.mark.asyncio
async def test_chat_retrieves_relevant_chunk(
    client, rag_user: User, session: AsyncSession
):
    """Con documento relevante, rag_used debe ser >= 1."""
    uid = rag_user.id

    await _seed_document(
        session,
        uid,
        title="Manual de cocina",
        chunks=[
            "La paella valenciana se prepara con arroz bomba y azafrán.",
            "El gazpacho andaluz se sirve frío en verano.",
            "Para hacer tortilla española se necesitan huevos y patatas.",
        ],
    )

    headers = {"X-Dev-User-Id": str(uid)}
    r = await client.post(
        "/api/v1/conversations", json={"title": "con doc"}, headers=headers
    )
    conv_id = r.json()["id"]

    # "documento" activa needs_rag. "paella" matchea por keyword con el chunk 0.
    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Según el documento, ¿cómo se prepara la paella?",
        },
        headers=headers,
    )
    assert r.status_code == 200
    events = await _read_sse(r)
    final = events[-1]
    assert final["type"] == "final"
    assert final["route"] in ("STANDARD", "DEEP")
    assert final["rag_used"] >= 1, (
        f"Esperaba rag_used>=1, llegó {final['rag_used']}"
    )


@pytest.mark.asyncio
async def test_chat_rag_isolated_between_users(
    client, session: AsyncSession
):
    """El documento de A no aparece en el contexto de B."""
    user_a = User(
        id=uuid.uuid4(),
        name="A",
        email=f"ra-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    user_b = User(
        id=uuid.uuid4(),
        name="B",
        email=f"rb-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add_all([user_a, user_b])
    await session.commit()

    # A tiene documento; B no
    await _seed_document(
        session,
        user_a.id,
        title="Secreto de A",
        chunks=["Información confidencial que solo A debería ver."],
    )

    headers_b = {"X-Dev-User-Id": str(user_b.id)}
    r = await client.post(
        "/api/v1/conversations", json={"title": "de B"}, headers=headers_b
    )
    conv_id = r.json()["id"]

    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Según el documento, resume la información confidencial",
        },
        headers=headers_b,
    )
    events = await _read_sse(r)
    final = events[-1]
    assert final["rag_used"] == 0


@pytest.mark.asyncio
async def test_chat_rag_and_memory_together(
    client, rag_user: User, session: AsyncSession
):
    """Un turno puede recuperar memoria y RAG a la vez."""
    uid = rag_user.id

    # Sembrar un documento
    await _seed_document(
        session,
        uid,
        title="Notas de proyecto",
        chunks=["El cliente pidió entrega para el 15 de marzo."],
    )

    # Sembrar una memoria
    from app.core.schemas.memory import MemoryCandidate
    from app.memory.store import MemoryStore
    mem_store = MemoryStore(session, FakeEmbeddingsProvider())
    await mem_store.create_from_candidate(
        uid,
        MemoryCandidate(
            type="PREFERENCE",
            content="Prefiere explicaciones concisas y directas",
            importance=0.9,
            confidence=0.9,
            source="EXPLICIT",
        ),
    )
    await session.commit()

    headers = {"X-Dev-User-Id": str(uid)}
    r = await client.post(
        "/api/v1/conversations", json={"title": "todo"}, headers=headers
    )
    conv_id = r.json()["id"]

    # Mensaje con marcador de memoria ("prefiero") y de RAG ("documento")
    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": (
                "Como te dije, prefiero explicaciones concisas. "
                "Según el documento, ¿cuándo es la entrega?"
            ),
        },
        headers=headers,
    )
    events = await _read_sse(r)
    final = events[-1]
    assert final["type"] == "final"
    # memory_used >= 1 porque matchea por keyword "explicaciones concisas"
    # rag_used >= 1 porque matchea por keyword "entrega"
    assert final["memory_used"] >= 1
    assert final["rag_used"] >= 1