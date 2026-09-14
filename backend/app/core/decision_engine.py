import re

from app.core.schemas.plan import Budget, ProcessingPlan

# Marcadores que empujan a rutas más profundas. Ampliables en Fase 4.
_DEEP_MARKERS = re.compile(
    r"\b(analiza|planifica|diseña|diseñar|arquitectura|estrategia|"
    r"refactoriza|multi[\s-]?paso|debug|depura|implementa|construye|integra)\b",
    re.IGNORECASE,
)
_KNOWLEDGE_MARKERS = re.compile(
    r"\b(según|documento|pdf|archivo|apuntes|manual|paper|art[íi]culo)\b",
    re.IGNORECASE,
)
_MEMORY_MARKERS = re.compile(
    r"\b(como te dije|como te coment[ée]|recuerda|record[áa]s|antes te|"
    r"prefiero|siempre|nunca|mi nombre es|me llamo|trabajo con|uso)\b",
    re.IGNORECASE,
)


class DecisionEngine:
    """Clasifica el turno y devuelve un ProcessingPlan.

    Estrategia (Fase 1, sin LLM):
      1. Heurísticas baratas por patrón + longitud + adjuntos.
      2. Fallback a STANDARD.
    En Fase 4 se añade similitud de embeddings y clasificador pequeño.
    """

    def plan_for(self, message: str, *, has_attachments: bool = False) -> ProcessingPlan:
        text = message.strip()
        length = len(text)

        # FAST: consultas muy cortas sin marcadores de conocimiento/memoria.
        looks_fast = (
            length <= 120
            and not has_attachments
            and not _KNOWLEDGE_MARKERS.search(text)
            and not _MEMORY_MARKERS.search(text)
            and not _DEEP_MARKERS.search(text)
        )
        if looks_fast:
            return ProcessingPlan(
                route="FAST",
                budget=Budget(max_tool_calls=0, max_latency_ms=8_000),
            )

        # DEEP: tareas complejas o con adjuntos grandes.
        if _DEEP_MARKERS.search(text) or (has_attachments and length > 200):
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

        # STANDARD: por defecto con memoria si se detecta contexto personal.
        return ProcessingPlan(
            route="STANDARD",
            needs_memory=bool(_MEMORY_MARKERS.search(text)),
            needs_rag=has_attachments or bool(_KNOWLEDGE_MARKERS.search(text)),
            budget=Budget(max_tool_calls=1, max_latency_ms=20_000),
        )