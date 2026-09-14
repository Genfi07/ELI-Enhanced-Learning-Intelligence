"""Clasificador de intención: embeddings + regex.

Diseño:
  - Estrategia principal (si el proveedor de embeddings NO es fake):
      · Embeber los ejemplos etiquetados UNA VEZ (lazy, cacheado).
      · Embeber el mensaje del usuario.
      · Voto por K vecinos más cercanos → ruta ganadora.
  - Fallback (siempre disponible):
      · Delegar al DecisionEngine (regex puro, sin red, sin coste).

La decisión de usar embeddings se toma mirando `embeddings.name`. Con el
FakeEmbeddingsProvider (dev/tests), siempre se va por fallback, porque
los vectores fake no tienen semántica real y darían rutas aleatorias.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.contracts.embeddings import EmbeddingsProvider
from app.core.decision_engine import DecisionEngine
from app.core.intent_examples import EXAMPLES_BY_ROUTE
from app.core.schemas.plan import Budget, ProcessingPlan
from app.observability.logging import get_logger

log = get_logger(__name__)

K_NEIGHBORS = 5
MIN_CONFIDENCE = 0.35


@dataclass
class _ExampleVector:
    route: str
    vector: list[float]


class HybridIntentClassifier:
    def __init__(
        self,
        embeddings: EmbeddingsProvider,
        fallback: DecisionEngine | None = None,
    ) -> None:
        self.embeddings = embeddings
        self.fallback = fallback or DecisionEngine()
        self._examples: list[_ExampleVector] | None = None

    async def classify(
        self, message: str, *, has_attachments: bool = False
    ) -> ProcessingPlan:
        if self.embeddings.name == "fake":
            return self.fallback.plan_for(message, has_attachments=has_attachments)

        try:
            route = await self._classify_by_embeddings(message)
        except Exception as exc:
            log.warning("intent_classifier_embeddings_failed", error=str(exc))
            route = None

        if route is None:
            return self.fallback.plan_for(message, has_attachments=has_attachments)

        return self._build_plan_for_route(route, has_attachments=has_attachments)

    async def _classify_by_embeddings(self, message: str) -> str | None:
        examples = await self._get_examples()
        if not examples:
            return None

        query_vec = await self.embeddings.embed(message)

        scored: list[tuple[float, str]] = []
        for ex in examples:
            sim = _cosine(query_vec, ex.vector)
            scored.append((sim, ex.route))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:K_NEIGHBORS]
        if not top:
            return None

        if top[0][0] < MIN_CONFIDENCE:
            return None

        votes: dict[str, int] = {}
        for _, route in top:
            votes[route] = votes.get(route, 0) + 1
        return max(votes.items(), key=lambda x: x[1])[0]

    async def _get_examples(self) -> list[_ExampleVector]:
        if self._examples is not None:
            return self._examples

        all_texts: list[str] = []
        all_routes: list[str] = []
        for route, texts in EXAMPLES_BY_ROUTE.items():
            for t in texts:
                all_texts.append(t)
                all_routes.append(route)

        vectors = await self.embeddings.embed_batch(all_texts)
        self._examples = [
            _ExampleVector(route=r, vector=v)
            for r, v in zip(all_routes, vectors, strict=True)
        ]
        log.info(
            "intent_examples_embedded",
            count=len(self._examples),
            dimension=self.embeddings.dimension,
        )
        return self._examples

    def _build_plan_for_route(
        self, route: str, *, has_attachments: bool
    ) -> ProcessingPlan:
        if route == "FAST":
            return ProcessingPlan(
                route="FAST",
                budget=Budget(max_tool_calls=0, max_latency_ms=8_000),
            )
        if route == "DEEP":
            return ProcessingPlan(
                route="DEEP",
                needs_memory=True,
                needs_rag=has_attachments,
                needs_tools=True,
                needs_planning=True,
                needs_validation=True,
                budget=Budget(
                    max_tool_calls=6, max_tokens=32_000, max_latency_ms=60_000
                ),
            )
        return ProcessingPlan(
            route="STANDARD",
            needs_memory=True,
            needs_rag=has_attachments,
            budget=Budget(max_tool_calls=1, max_latency_ms=20_000),
        )


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)