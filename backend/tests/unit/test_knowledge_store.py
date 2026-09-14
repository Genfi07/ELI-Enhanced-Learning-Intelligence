"""Tests del KnowledgeStore.

Usan la sesión de test y FakeEmbeddingsProvider. Cubren:
  - CRUD de documentos.
  - Aislamiento entre usuarios.
  - Inserción de chunks.
  - Búsqueda híbrida (con keyword + vectorial).
  - Rechazo de documentos no READY en la búsqueda.
  - Borrado en cascada de chunks.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import DocumentChunk
from app.db.models.user import User
from app.llm.embeddings_fake import FakeEmbeddingsProvider
from app.rag.store import KnowledgeStore
from tests.conftest import ROLE_USER_ID


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
async def k_user(session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        name="Knowledge User",
        email=f"kn-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


@pytest.fixture
async def other_user(session: AsyncSession) -> User:
    """Segundo usuario REAL, para tests de aislamiento.

    Necesario porque la tabla `documents` tiene FK a `users` con
    ON DELETE CASCADE: no podemos insertar un documento cuyo dueño no exista.
    """
    u = User(
        id=uuid.uuid4(),
        name="Other User",
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


@pytest.fixture
def store(session: AsyncSession) -> KnowledgeStore:
    return KnowledgeStore(session, FakeEmbeddingsProvider())


# --------------------------------------------------------------------------- #
# CRUD documentos
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_and_get_document(session, k_user, store):
    doc = await store.create_document(
        k_user.id,
        title="Informe trimestral",
        mime_type="application/pdf",
        size_bytes=12345,
        storage_path="documents/abc/original.pdf",
    )
    await session.commit()

    fetched = await store.get_document(k_user.id, doc.id)
    assert fetched is not None
    assert fetched.title == "Informe trimestral"
    assert fetched.status == "PENDING"


@pytest.mark.asyncio
async def test_get_document_isolated_by_user(session, k_user, store):
    doc = await store.create_document(
        k_user.id, title="Privado", mime_type="text/plain",
        size_bytes=10, storage_path="documents/x/y.txt",
    )
    await session.commit()

    other_id = uuid.uuid4()
    assert await store.get_document(other_id, doc.id) is None


@pytest.mark.asyncio
async def test_list_documents_only_own(session, k_user, other_user, store):
    await store.create_document(
        k_user.id, title="Mío", mime_type="text/plain",
        size_bytes=1, storage_path="documents/a/a.txt",
    )
    await store.create_document(
        other_user.id, title="Ajeno", mime_type="text/plain",
        size_bytes=1, storage_path="documents/b/b.txt",
    )
    await session.commit()

    mine = await store.list_documents(k_user.id)
    titles = [d.title for d in mine]
    assert "Mío" in titles
    assert "Ajeno" not in titles


@pytest.mark.asyncio
async def test_update_status(session, k_user, store):
    doc = await store.create_document(
        k_user.id, title="X", mime_type="text/plain",
        size_bytes=1, storage_path="documents/x/x.txt",
    )
    await session.commit()

    await store.update_status(doc.id, "READY", chunk_count=7)
    await session.commit()

    fetched = await store.get_document(k_user.id, doc.id)
    assert fetched.status == "READY"
    assert fetched.chunk_count == 7


@pytest.mark.asyncio
async def test_delete_document_cascades_chunks(session, k_user, store):
    """Al borrar el documento, sus chunks se borran por cascade.

    NOTA: filtramos por document_id porque la tabla `document_chunks` es
    compartida con otros tests de la suite (que siembran sus propios chunks
    y no los limpian). Un `select(DocumentChunk)` sin filtro vería chunks
    ajenos y el test fallaría según el orden de ejecución.
    """
    doc = await store.create_document(
        k_user.id, title="Borrable", mime_type="text/plain",
        size_bytes=1, storage_path="documents/d/d.txt",
    )
    await session.commit()

    await store.insert_chunks(
        doc.id,
        [{"chunk_index": 0, "content": "hola", "token_count": 1,
          "meta": {}, "embedding": [0.1] * 1536}],
    )
    await session.commit()

    # Verificamos que existe antes
    before = list((await session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    )).all())
    assert len(before) == 1

    await store.delete_document(k_user.id, doc.id)
    await session.commit()

    # Los chunks del documento borrado ya no existen
    after = list((await session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    )).all())
    assert after == []


# --------------------------------------------------------------------------- #
# Chunks + búsqueda
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_insert_chunks_and_search_by_keyword(session, k_user, store):
    doc = await store.create_document(
        k_user.id, title="Manual", mime_type="text/plain",
        size_bytes=1, storage_path="documents/m/m.txt",
    )
    await session.commit()

    emb_provider = FakeEmbeddingsProvider()
    emb1 = await emb_provider.embed("El café de Colombia es famoso")
    emb2 = await emb_provider.embed("Los coches eléctricos son el futuro")

    await store.insert_chunks(
        doc.id,
        [
            {"chunk_index": 0, "content": "El café de Colombia es famoso",
             "token_count": 8, "meta": {"page": 1}, "embedding": emb1},
            {"chunk_index": 1, "content": "Los coches eléctricos son el futuro",
             "token_count": 8, "meta": {"page": 2}, "embedding": emb2},
        ],
    )
    await store.update_status(doc.id, "READY", chunk_count=2)
    await session.commit()

    results = await store.search(k_user.id, "café Colombia")
    assert len(results) >= 1
    assert any("café" in r.content.lower() for r in results)
    assert all(r.document_title == "Manual" for r in results)


@pytest.mark.asyncio
async def test_search_ignores_non_ready(session, k_user, store):
    doc = await store.create_document(
        k_user.id, title="Pendiente", mime_type="text/plain",
        size_bytes=1, storage_path="documents/p/p.txt",
    )
    await session.commit()

    emb = await FakeEmbeddingsProvider().embed("texto irrelevante")
    await store.insert_chunks(
        doc.id,
        [{"chunk_index": 0, "content": "contenido secreto uno",
          "token_count": 3, "meta": {}, "embedding": emb}],
    )
    # NO marcamos como READY (se queda en PENDING)
    await session.commit()

    results = await store.search(k_user.id, "contenido secreto")
    assert results == []


@pytest.mark.asyncio
async def test_search_isolated_between_users(
    session, k_user, other_user, store
):
    doc = await store.create_document(
        k_user.id, title="Doc de K", mime_type="text/plain",
        size_bytes=1, storage_path="documents/k/k.txt",
    )
    await session.commit()

    emb = await FakeEmbeddingsProvider().embed("contenido de K")
    await store.insert_chunks(
        doc.id,
        [{"chunk_index": 0, "content": "contenido de K",
          "token_count": 3, "meta": {}, "embedding": emb}],
    )
    await store.update_status(doc.id, "READY", chunk_count=1)
    await session.commit()

    # El otro usuario no debe ver nada
    results = await store.search(other_user.id, "contenido")
    assert results == []