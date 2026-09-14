"""MemoryConsolidator: decide CREATE / IGNORE / SUPERSEDE.

Diseño:
  - `decide()` es una función pura: recibe candidato + vecinos, devuelve decisión.
    Toda la lógica crítica vive aquí, es fácil de testear y auditar.
  - `MemoryConsolidator.consolidate()` orquesta: busca vecinos en el store,
    llama a `decide()`, ejecuta la acción y registra eventos.

Importante:
  Las comparaciones usan `similarity` (similitud coseno cruda), NO `score`
  (composite). El score compuesto es para ranking de contexto; mezclarlo aquí
  haría que duplicados exactos nunca superen el umbral.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from app.core.schemas.memory import MemoryCandidate
from app.db.models.memory import Memory
from app.memory.store import MemoryStore, ScoredMemory
from app.observability.logging import get_logger

log = get_logger(__name__)

Action = Literal["CREATE", "IGNORE", "SUPERSEDE"]

# Umbrales por defecto. Se pueden sobreescribir en el constructor.
DEFAULT_DUPLICATE_THRESHOLD = 0.95
DEFAULT_SUPERSEDE_THRESHOLD = 0.85


@dataclass
class ConsolidationDecision:
    action: Action
    target_memory_id: uuid.UUID | None = None
    reason: str = ""


@dataclass
class ConsolidationResult:
    action: Action
    memory: Memory
    candidate: MemoryCandidate


def decide(
    candidate: MemoryCandidate,
    neighbors: list[ScoredMemory],
    *,
    duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
    supersede_threshold: float = DEFAULT_SUPERSEDE_THRESHOLD,
) -> ConsolidationDecision:
    """Decide qué hacer con un candidato dados sus vecinos cercanos del mismo tipo.

    Esta función es pura: no toca BD, no llama a servicios externos.
    """
    if not neighbors:
        return ConsolidationDecision(action="CREATE", reason="no neighbors")

    # Vecino con similitud coseno más alta.
    best = max(neighbors, key=lambda n: n.similarity)

    if best.similarity >= duplicate_threshold:
        return ConsolidationDecision(
            action="IGNORE",
            target_memory_id=best.memory.id,
            reason=f"duplicate of existing (similarity={best.similarity:.2f})",
        )

    if best.similarity >= supersede_threshold:
        return ConsolidationDecision(
            action="SUPERSEDE",
            target_memory_id=best.memory.id,
            reason=f"supersedes previous (similarity={best.similarity:.2f})",
        )

    return ConsolidationDecision(
        action="CREATE",
        reason=f"no close match (best similarity={best.similarity:.2f})",
    )


class MemoryConsolidator:
    def __init__(
        self,
        store: MemoryStore,
        *,
        duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
        supersede_threshold: float = DEFAULT_SUPERSEDE_THRESHOLD,
        neighbor_pool: int = 5,
    ) -> None:
        self.store = store
        self.duplicate_threshold = duplicate_threshold
        self.supersede_threshold = supersede_threshold
        self.neighbor_pool = neighbor_pool

    async def consolidate(
        self,
        user_id: uuid.UUID,
        candidates: list[MemoryCandidate],
        *,
        source_conversation_id: uuid.UUID | None = None,
    ) -> list[ConsolidationResult]:
        results: list[ConsolidationResult] = []
        for cand in candidates:
            result = await self._process_one(
                user_id, cand, source_conversation_id=source_conversation_id
            )
            results.append(result)
        return results

    async def _process_one(
        self,
        user_id: uuid.UUID,
        candidate: MemoryCandidate,
        *,
        source_conversation_id: uuid.UUID | None,
    ) -> ConsolidationResult:
        # Buscamos vecinos cercanos al contenido del candidato
        neighbors_raw = await self.store.search(
            user_id, candidate.content, top_k=self.neighbor_pool
        )
        # Filtramos al MISMO tipo: un FACT no debe anular una PREFERENCE
        neighbors = [n for n in neighbors_raw if n.memory.type == candidate.type]

        decision = decide(
            candidate,
            neighbors,
            duplicate_threshold=self.duplicate_threshold,
            supersede_threshold=self.supersede_threshold,
        )

        if decision.action == "IGNORE":
            assert decision.target_memory_id is not None
            existing = await self.store.get(user_id, decision.target_memory_id)
            if existing is None:
                # Race condition improbable: cae a CREATE
                log.warning(
                    "consolidate_ignore_target_missing",
                    target=str(decision.target_memory_id),
                )
                created = await self.store.create_from_candidate(
                    user_id, candidate,
                    source_conversation_id=source_conversation_id,
                )
                return ConsolidationResult("CREATE", created, candidate)
            log.info(
                "memory_ignored",
                memory_id=str(existing.id),
                reason=decision.reason,
            )
            return ConsolidationResult("IGNORE", existing, candidate)

        if decision.action == "SUPERSEDE":
            assert decision.target_memory_id is not None
            new_mem = await self.store.create_from_candidate(
                user_id, candidate, source_conversation_id=source_conversation_id
            )
            await self.store.supersede(
                user_id,
                old_id=decision.target_memory_id,
                new_id=new_mem.id,
                reason=decision.reason,
            )
            log.info(
                "memory_superseded",
                old_id=str(decision.target_memory_id),
                new_id=str(new_mem.id),
                reason=decision.reason,
            )
            return ConsolidationResult("SUPERSEDE", new_mem, candidate)

        # CREATE
        new_mem = await self.store.create_from_candidate(
            user_id, candidate, source_conversation_id=source_conversation_id
        )
        return ConsolidationResult("CREATE", new_mem, candidate)