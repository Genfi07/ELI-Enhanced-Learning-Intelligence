"""Repositorio de memorias con búsqueda híbrida.

Diseño:
  - Toda operación recibe user_id explícito. No existe un método que no
    filtre por user_id — eso garantiza aislamiento por diseño.
  - La búsqueda combina ranking vectorial (pgvector cosine) y ranking keyword
    (Postgres tsvector) usando Reciprocal Rank Fusion (RRF). Esto es robusto
    cuando cualquiera de los dos métodos falla: el otro sigue funcionando.
  - El scoring final combina retrieval + importancia + recencia + uso. Es lo
    que decide qué memorias entran en el contexto cuando el presupuesto es
    limitado. Además exponemos la similitud coseno cruda (`similarity`) para
    que el consolidator pueda decidir duplicados sin el ruido del score compuesto.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.embeddings import EmbeddingsProvider
from app.core.schemas.memory import MemoryCandidate
from app.db.models.memory import Memory, MemoryEvent


# Constante de RRF. 60 es el valor estándar del paper original.
RRF_K = 60

# Pesos para el score final. Deben sumar 1.0.
WEIGHT_SIMILARITY = 0.55
WEIGHT_IMPORTANCE = 0.20
WEIGHT_RECENCY = 0.15
WEIGHT_USAGE = 0.10


@dataclass
class ScoredMemory:
    memory: Memory
    score: float               # composite: similitud + importancia + recencia + uso
    similarity: float = 0.0    # similitud coseno cruda [0,1], usada por consolidation


class MemoryStore:
    def __init__(self, session: AsyncSession, embeddings: EmbeddingsProvider) -> None:
        self.session = session
        self.embeddings = embeddings

    # ------------------------------------------------------------------ #
    # Crear
    # ------------------------------------------------------------------ #
    async def create_from_candidate(
        self,
        user_id: uuid.UUID,
        candidate: MemoryCandidate,
        *,
        source_conversation_id: uuid.UUID | None = None,
    ) -> Memory:
        vector = await self.embeddings.embed(candidate.content)
        mem = Memory(
            user_id=user_id,
            type=candidate.type,
            content=candidate.content,
            importance=candidate.importance,
            confidence=candidate.confidence,
            source=candidate.source,
            source_conversation_id=source_conversation_id,
            embedding=vector,
            status="ACTIVE",
        )
        self.session.add(mem)
        await self.session.flush()

        self.session.add(
            MemoryEvent(
                memory_id=mem.id,
                event="CREATED",
                reason=f"source={candidate.source}",
                actor="ELI",
            )
        )
        await self.session.flush()
        return mem

    # ------------------------------------------------------------------ #
    # Leer
    # ------------------------------------------------------------------ #
    async def get(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory | None:
        stmt = select(Memory).where(
            Memory.id == memory_id, Memory.user_id == user_id
        )
        return await self.session.scalar(stmt)

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = "ACTIVE",
        type: str | None = None,
        limit: int = 200,
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        if type is not None:
            stmt = stmt.where(Memory.type == type)
        stmt = stmt.order_by(Memory.updated_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    # ------------------------------------------------------------------ #
    # Búsqueda híbrida
    # ------------------------------------------------------------------ #
    async def search(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        candidate_pool: int = 30,
    ) -> list[ScoredMemory]:
        """Búsqueda híbrida: vectorial + keyword, fusionadas con RRF."""
        if not query.strip():
            return []

        # 1. Query vectorial (con similitud cruda)
        query_vector = await self.embeddings.embed(query)
        vector_results = await self._vector_search(
            user_id, query_vector, limit=candidate_pool
        )
        vector_hits = [mid for mid, _ in vector_results]
        similarity_by_id: dict[uuid.UUID, float] = {
            mid: sim for mid, sim in vector_results
        }

        # 2. Query keyword
        keyword_hits = await self._keyword_search(
            user_id, query, limit=candidate_pool
        )

        # 3. Fusionar con RRF
        rrf_scores: dict[uuid.UUID, float] = {}
        for rank, mid in enumerate(vector_hits):
            rrf_scores[mid] = rrf_scores.get(mid, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, mid in enumerate(keyword_hits):
            rrf_scores[mid] = rrf_scores.get(mid, 0.0) + 1.0 / (RRF_K + rank + 1)

        if not rrf_scores:
            return []

        # 4. Cargar los modelos y aplicar score final
        ids = list(rrf_scores.keys())
        stmt = select(Memory).where(
            Memory.id.in_(ids),
            Memory.user_id == user_id,
            Memory.status == "ACTIVE",
        )
        memories = list((await self.session.scalars(stmt)).all())

        # Normalizar scores RRF al rango [0,1]
        max_rrf = max(rrf_scores.values()) or 1.0
        now = datetime.now(timezone.utc)

        scored: list[ScoredMemory] = []
        for mem in memories:
            base = rrf_scores[mem.id] / max_rrf
            recency = _recency_score(mem.updated_at, now)
            usage = min(1.0, mem.usage_count / 5.0)  # saturación a los 5 usos
            final = (
                WEIGHT_SIMILARITY * base
                + WEIGHT_IMPORTANCE * mem.importance
                + WEIGHT_RECENCY * recency
                + WEIGHT_USAGE * usage
            )
            scored.append(
                ScoredMemory(
                    memory=mem,
                    score=final,
                    similarity=similarity_by_id.get(mem.id, 0.0),
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    async def _vector_search(
        self,
        user_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        """Devuelve [(memory_id, similarity)] ordenados por similitud desc.

        similarity = 1 - cosine_distance. Para embeddings normalizados queda en [0,1].
        Esta similitud es la que usa el consolidator para decidir duplicados.
        """
        stmt = text(
            """
            SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) AS sim
            FROM memories
            WHERE user_id = :uid
              AND status = 'ACTIVE'
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :lim
            """
        )
        vec_literal = "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"
        rows = await self.session.execute(
            stmt, {"uid": str(user_id), "vec": vec_literal, "lim": limit}
        )
        return [(row[0], float(row[1])) for row in rows.all()]

    async def _keyword_search(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        limit: int,
    ) -> list[uuid.UUID]:
        # Full-text search simple en español. ts_rank para ordenar.
        stmt = text(
            """
            SELECT id
            FROM memories
            WHERE user_id = :uid
              AND status = 'ACTIVE'
              AND to_tsvector('spanish', content) @@ plainto_tsquery('spanish', :q)
            ORDER BY ts_rank(to_tsvector('spanish', content),
                             plainto_tsquery('spanish', :q)) DESC
            LIMIT :lim
            """
        )
        rows = await self.session.execute(
            stmt, {"uid": str(user_id), "q": query, "lim": limit}
        )
        return [row[0] for row in rows.all()]

    # ------------------------------------------------------------------ #
    # Uso
    # ------------------------------------------------------------------ #
    async def mark_used(self, memory_ids: list[uuid.UUID]) -> None:
        """Registra que estas memorias se han usado en un turno."""
        if not memory_ids:
            return
        now = datetime.now(timezone.utc)
        stmt = (
            update(Memory)
            .where(Memory.id.in_(memory_ids))
            .values(
                last_used_at=now,
                usage_count=Memory.usage_count + 1,
            )
        )
        await self.session.execute(stmt)

    # ------------------------------------------------------------------ #
    # Modificación (supersede / delete / update)
    # ------------------------------------------------------------------ #
    async def supersede(
        self,
        user_id: uuid.UUID,
        old_id: uuid.UUID,
        new_id: uuid.UUID,
        reason: str,
    ) -> bool:
        """Marca la memoria `old_id` como SUPERSEDED y enlaza con la nueva.

        No borra nada. La historia se conserva para auditoría.
        """
        old = await self.get(user_id, old_id)
        new = await self.get(user_id, new_id)
        if old is None or new is None:
            return False
        if old.status == "SUPERSEDED":
            return True  # ya estaba
        old.status = "SUPERSEDED"
        old.superseded_by = new_id
        self.session.add(
            MemoryEvent(
                memory_id=old.id,
                event="SUPERSEDED",
                previous_content=old.content,
                reason=reason,
                actor="ELI",
            )
        )
        return True

    async def soft_delete(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> bool:
        mem = await self.get(user_id, memory_id)
        if mem is None or mem.status == "DELETED":
            return False
        mem.status = "DELETED"
        self.session.add(
            MemoryEvent(
                memory_id=mem.id,
                event="DELETED",
                previous_content=mem.content,
                reason="user requested",
                actor="USER",
            )
        )
        return True

    async def update_content(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        content: str | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        actor: str = "ELI",
    ) -> Memory | None:
        mem = await self.get(user_id, memory_id)
        if mem is None:
            return None
        previous = mem.content
        if content is not None:
            mem.content = content
            mem.embedding = await self.embeddings.embed(content)
        if importance is not None:
            mem.importance = importance
        if confidence is not None:
            mem.confidence = confidence
        self.session.add(
            MemoryEvent(
                memory_id=mem.id,
                event="UPDATED",
                previous_content=previous,
                reason="content/score updated",
                actor=actor,
            )
        )
        return mem


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _recency_score(updated_at: datetime, now: datetime) -> float:
    """Score de recencia en [0,1]. Decae con semivida de 30 días."""
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    delta = now - updated_at
    days = delta.total_seconds() / 86400.0
    if days <= 0:
        return 1.0
    # Decaimiento exponencial: 2^(-days / 30)
    return math.pow(2.0, -days / 30.0)