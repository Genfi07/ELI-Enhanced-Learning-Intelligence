"""KnowledgeStore: repositorio de documentos y búsqueda híbrida sobre chunks.

Ciclo de vida efímero:
  - Los documentos "activos" son los que tienen deleted_at IS NULL y
    hidden_at IS NULL.
  - Los documentos "eliminados" tienen deleted_at pero no hidden_at.
    Ya no aparecen en búsquedas (sus chunks fueron borrados).
  - Los documentos "ocultos" tienen hidden_at.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.embeddings import EmbeddingsProvider
from app.core.schemas.document import RetrievedChunk
from app.db.models.document import Document, DocumentChunk
from app.observability.logging import get_logger

log = get_logger(__name__)

RRF_K = 60


@dataclass
class ScoredChunk:
    chunk: DocumentChunk
    score: float
    similarity: float


class KnowledgeStore:
    def __init__(self, session: AsyncSession, embeddings: EmbeddingsProvider) -> None:
        self.session = session
        self.embeddings = embeddings

    # ------------------------------------------------------------------ #
    # Documentos — creación y lectura
    # ------------------------------------------------------------------ #
    async def create_document(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        mime_type: str,
        size_bytes: int,
        storage_path: str,
        source_type: str = "UPLOAD",
        scope: str = "USER",
        org_id: uuid.UUID | None = None,
        meta: dict | None = None,
    ) -> Document:
        doc = Document(
            owner_user_id=user_id,
            org_id=org_id,
            scope=scope,
            title=title[:300],
            source_type=source_type,
            mime_type=mime_type,
            size_bytes=size_bytes,
            storage_path=storage_path,
            status="PENDING",
            meta=meta or {},
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.owner_user_id == user_id,
        )
        return await self.session.scalar(stmt)

    async def list_documents(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Document]:
        stmt = select(Document).where(
            Document.owner_user_id == user_id,
            Document.hidden_at.is_(None),
        )
        if status:
            stmt = stmt.where(Document.status == status)
        stmt = stmt.order_by(Document.updated_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def list_documents_by_state(
        self,
        user_id: uuid.UUID,
        *,
        state: str = "active",
        limit: int = 100,
    ) -> list[Document]:
        base = select(Document).where(Document.owner_user_id == user_id)

        if state == "active":
            base = base.where(
                Document.deleted_at.is_(None),
                Document.hidden_at.is_(None),
            )
        elif state == "deleted":
            base = base.where(
                Document.deleted_at.is_not(None),
                Document.hidden_at.is_(None),
            )
        elif state == "all":
            base = base.where(Document.hidden_at.is_(None))
        else:
            base = base.where(
                Document.deleted_at.is_(None),
                Document.hidden_at.is_(None),
            )

        base = base.order_by(Document.updated_at.desc()).limit(limit)
        return list((await self.session.scalars(base)).all())

    # ------------------------------------------------------------------ #
    # Documentos — mutaciones
    # ------------------------------------------------------------------ #
    async def update_status(
        self,
        document_id: uuid.UUID,
        status: str,
        *,
        error: str | None = None,
        chunk_count: int | None = None,
        meta_patch: dict | None = None,
    ) -> None:
        doc = await self.session.get(Document, document_id)
        if doc is None:
            return
        doc.status = status
        if error is not None:
            doc.error = error[:2000]
        elif status != "FAILED":
            doc.error = None
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        if meta_patch:
            doc.meta = {**doc.meta, **meta_patch}

    async def delete_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        doc = await self.get_document(user_id, document_id)
        if doc is None:
            return None
        await self.session.delete(doc)
        return doc

    async def soft_delete_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        doc = await self.get_document(user_id, document_id)
        if doc is None:
            return None
        await self.delete_chunks_for_document(document_id)
        doc.deleted_at = datetime.now(timezone.utc)
        doc.chunk_count = 0
        await self.session.flush()
        return doc

    async def hide_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        doc = await self.get_document(user_id, document_id)
        if doc is None:
            return None
        doc.hidden_at = datetime.now(timezone.utc)
        await self.session.flush()
        return doc

    async def mark_physical_deleted(self, document_id: uuid.UUID) -> None:
        doc = await self.session.get(Document, document_id)
        if doc is None:
            return
        doc.physical_deleted_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def update_summary_and_topics(
        self,
        document_id: uuid.UUID,
        *,
        summary: str | None,
        topics: list[str],
    ) -> None:
        doc = await self.session.get(Document, document_id)
        if doc is None:
            return
        doc.summary = (summary or "")[:2000] or None
        doc.topics = topics
        await self.session.flush()

    # ------------------------------------------------------------------ #
    # Chunks
    # ------------------------------------------------------------------ #
    async def insert_chunks(
        self,
        document_id: uuid.UUID,
        chunks: list[dict],
    ) -> int:
        if not chunks:
            return 0
        models = [
            DocumentChunk(
                document_id=document_id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                token_count=c.get("token_count", 0),
                embedding=c.get("embedding"),
                meta=c.get("meta", {}),
            )
            for c in chunks
        ]
        self.session.add_all(models)
        await self.session.flush()
        return len(models)

    async def delete_chunks_for_document(self, document_id: uuid.UUID) -> int:
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def get_chunks_for_documents(
        self,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID],
        *,
        limit_per_doc: int = 20,
    ) -> list[RetrievedChunk]:
        """Devuelve los primeros N chunks de cada documento adjunto.

        Usado cuando el usuario adjunta un documento al chat SIN preguntar
        algo específico. Devolvemos el contenido completo del documento
        (hasta `limit_per_doc` chunks por doc) para que ELI lo tenga todo
        disponible.

        Solo devuelve documentos activos (READY, no eliminados, no ocultos).
        """
        if not document_ids:
            return []

        # Filtro de seguridad: solo los documentos del usuario que estén activos.
        docs_stmt = select(Document).where(
            Document.id.in_(document_ids),
            Document.owner_user_id == user_id,
            Document.status == "READY",
            Document.deleted_at.is_(None),
            Document.hidden_at.is_(None),
        )
        docs = list((await self.session.scalars(docs_stmt)).all())
        if not docs:
            return []

        valid_ids = [d.id for d in docs]
        doc_by_id = {d.id: d for d in docs}

        results: list[RetrievedChunk] = []
        for doc_id in valid_ids:
            chunks_stmt = (
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(limit_per_doc)
            )
            chunks = list((await self.session.scalars(chunks_stmt)).all())
            doc = doc_by_id[doc_id]
            for c in chunks:
                results.append(
                    RetrievedChunk(
                        chunk_id=c.id,
                        document_id=c.document_id,
                        document_title=doc.title,
                        content=c.content,
                        score=1.0,
                        similarity=1.0,
                        meta=c.meta or {},
                    )
                )
        return results

    # ------------------------------------------------------------------ #
    # Búsqueda híbrida
    # ------------------------------------------------------------------ #
    async def search(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 6,
        candidate_pool: int = 30,
        org_id: uuid.UUID | None = None,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[RetrievedChunk]:
        """Búsqueda híbrida sobre documentos activos.

        Si `document_ids` está definido, restringe la búsqueda SOLO a esos
        documentos. Útil para búsquedas dentro de adjuntos específicos.
        """
        if not query.strip():
            return []

        query_vector = await self.embeddings.embed(query)

        vector_hits = await self._vector_search(
            user_id,
            query_vector,
            limit=candidate_pool,
            org_id=org_id,
            document_ids=document_ids,
        )
        similarity_by_id: dict[uuid.UUID, float] = {cid: sim for cid, sim in vector_hits}
        vector_ids = [cid for cid, _ in vector_hits]

        keyword_ids = await self._keyword_search(
            user_id,
            query,
            limit=candidate_pool,
            org_id=org_id,
            document_ids=document_ids,
        )

        rrf: dict[uuid.UUID, float] = {}
        for rank, cid in enumerate(vector_ids):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, cid in enumerate(keyword_ids):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)

        if not rrf:
            return []

        ids = list(rrf.keys())
        stmt = select(DocumentChunk).where(DocumentChunk.id.in_(ids))
        chunks = list((await self.session.scalars(stmt)).all())
        chunks_by_id = {c.id: c for c in chunks}

        doc_ids = list({c.document_id for c in chunks})
        docs = list(
            (
                await self.session.scalars(
                    select(Document).where(Document.id.in_(doc_ids))
                )
            ).all()
        )
        doc_by_id = {d.id: d for d in docs}

        max_rrf = max(rrf.values()) or 1.0
        results: list[RetrievedChunk] = []
        for cid, rrf_score in rrf.items():
            chunk = chunks_by_id.get(cid)
            if chunk is None:
                continue
            doc = doc_by_id.get(chunk.document_id)
            if doc is None:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=doc.title,
                    content=chunk.content,
                    score=rrf_score / max_rrf,
                    similarity=similarity_by_id.get(cid, 0.0),
                    meta=chunk.meta or {},
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def _vector_search(
        self,
        user_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int,
        org_id: uuid.UUID | None,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[tuple[uuid.UUID, float]]:
        scope_sql, params = _scope_filter(user_id, org_id)

        # Filtro adicional: solo a documentos específicos (si se pasa).
        doc_filter_sql = ""
        if document_ids:
            doc_ids_str = ",".join(f"'{str(d)}'" for d in document_ids)
            doc_filter_sql = f"AND d.id IN ({doc_ids_str})"

        stmt = text(
            f"""
            SELECT dc.id, 1 - (dc.embedding <=> CAST(:vec AS vector)) AS sim
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE dc.embedding IS NOT NULL
              AND d.status = 'READY'
              AND d.deleted_at IS NULL
              AND d.hidden_at IS NULL
              {doc_filter_sql}
              AND ({scope_sql})
            ORDER BY dc.embedding <=> CAST(:vec AS vector)
            LIMIT :lim
            """
        )
        vec_literal = "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"
        params.update({"vec": vec_literal, "lim": limit})
        rows = await self.session.execute(stmt, params)
        return [(row[0], float(row[1])) for row in rows.all()]

    async def _keyword_search(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        limit: int,
        org_id: uuid.UUID | None,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[uuid.UUID]:
        scope_sql, params = _scope_filter(user_id, org_id)

        doc_filter_sql = ""
        if document_ids:
            doc_ids_str = ",".join(f"'{str(d)}'" for d in document_ids)
            doc_filter_sql = f"AND d.id IN ({doc_ids_str})"

        stmt = text(
            f"""
            SELECT dc.id
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.status = 'READY'
              AND d.deleted_at IS NULL
              AND d.hidden_at IS NULL
              {doc_filter_sql}
              AND ({scope_sql})
              AND to_tsvector('spanish', dc.content) @@
                  plainto_tsquery('spanish', :q)
            ORDER BY ts_rank(
                to_tsvector('spanish', dc.content),
                plainto_tsquery('spanish', :q)
            ) DESC
            LIMIT :lim
            """
        )
        params.update({"q": query, "lim": limit})
        rows = await self.session.execute(stmt, params)
        return [row[0] for row in rows.all()]


def _scope_filter(user_id: uuid.UUID, org_id: uuid.UUID | None) -> tuple[str, dict]:
    parts = ["(d.scope = 'USER' AND d.owner_user_id = :uid)"]
    params: dict = {"uid": str(user_id)}
    if org_id is not None:
        parts.append("(d.scope = 'ORG' AND d.org_id = :oid)")
        params["oid"] = str(org_id)
    parts.append("(d.scope = 'GLOBAL')")
    return " OR ".join(parts), params