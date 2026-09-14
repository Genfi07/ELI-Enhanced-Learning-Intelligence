"""Tests del HybridIntentClassifier."""
from __future__ import annotations

import pytest

from app.core.intent_classifier import HybridIntentClassifier
from app.llm.embeddings_fake import FakeEmbeddingsProvider


class ToyEmbeddings:
    name = "toy"
    dimension = 3

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    async def embed(self, text: str) -> list[float]:
        return self.mapping.get(text, [0.1, 0.1, 0.1])

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


# --------------------------------------------------------------------------- #
# Fallback con FakeEmbeddings
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_fake_embeddings_delegates_to_regex():
    clf = HybridIntentClassifier(FakeEmbeddingsProvider())
    assert (await clf.classify("Hola")).route == "FAST"
    assert (await clf.classify("Como te dije, prefiero paso a paso")).route == "STANDARD"
    assert (
        await clf.classify("Analiza mi proyecto y diseña la arquitectura completa")
    ).route == "DEEP"


# --------------------------------------------------------------------------- #
# Clasificación por embeddings (toy)
# --------------------------------------------------------------------------- #
_ALL_FAST = [
    "¿Cuánto es 25 por 4?", "Hola", "¿Qué hora es?", "Dime un chiste corto",
    "Traduce 'hola' al inglés", "¿Cuál es la capital de Francia?",
    "Convierte 100 dólares a euros", "Buenos días", "Gracias",
    "¿Quién escribió el Quijote?", "Dame un número aleatorio del 1 al 10",
    "¿Cuántos días tiene un año?",
]
_ALL_STD = [
    "Como te dije antes, prefiero explicaciones paso a paso",
    "Recuérdame qué proyectos tengo pendientes",
    "Según el documento que subí, resume los puntos clave",
    "¿Qué sabes de mí?",
    "¿Puedes explicarme esto con el estilo que te pedí?",
    "Como comentamos la última vez, sigo con lo mismo",
    "Resume el archivo PDF que te compartí",
    "Prefiero respuestas en español neutro",
    "¿Qué me habías dicho sobre este tema?",
    "Basándote en lo que sabes de mí, ¿qué me recomiendas?",
    "Ayúdame a entender esto aplicando mi contexto",
    "Teniendo en cuenta mis preferencias, ¿qué opción me conviene?",
]
_ALL_DEEP = [
    "Analiza mi proyecto y dime cómo convertirlo en una plataforma comercial",
    "Diseña la arquitectura de un sistema de inventario para mi empresa",
    "Planifica los pasos para lanzar un producto al mercado",
    "Compara estas tres opciones y recomiéndame la mejor con justificación",
    "Refactoriza este código y explica qué cambios haces y por qué",
    "Diseña un plan de estudio de 3 meses para aprender machine learning",
    "Construye un roadmap técnico para escalar esta aplicación",
    "Implementa una estrategia completa de marketing digital para una startup",
    "Ayúdame a depurar esta funcionalidad compleja paso a paso",
    "Evalúa los riesgos de esta decisión estratégica y sugiere mitigaciones",
    "Divide este problema complejo en subproblemas manejables",
    "Arquitectura de microservicios para un sistema de pagos con alta disponibilidad",
]


def _mapping() -> dict[str, list[float]]:
    m: dict[str, list[float]] = {}
    for t in _ALL_FAST:
        m[t] = [1.0, 0.0, 0.0]
    for t in _ALL_STD:
        m[t] = [0.0, 1.0, 0.0]
    for t in _ALL_DEEP:
        m[t] = [0.0, 0.0, 1.0]
    m["Cuánto es 7+7"] = [1.0, 0.0, 0.0]
    m["Recuérdame mis metas"] = [0.0, 1.0, 0.0]
    m["Diseña un plan completo de negocio"] = [0.0, 0.0, 1.0]
    return m


@pytest.mark.asyncio
async def test_embeddings_classification():
    clf = HybridIntentClassifier(ToyEmbeddings(_mapping()))
    assert (await clf.classify("Cuánto es 7+7")).route == "FAST"
    assert (await clf.classify("Recuérdame mis metas")).route == "STANDARD"
    assert (await clf.classify("Diseña un plan completo de negocio")).route == "DEEP"


@pytest.mark.asyncio
async def test_embeddings_exception_falls_back():
    class BrokenEmbeddings:
        name = "broken"
        dimension = 3
        async def embed(self, text): raise RuntimeError("boom")
        async def embed_batch(self, texts): raise RuntimeError("boom")

    clf = HybridIntentClassifier(BrokenEmbeddings())
    plan = await clf.classify("Analiza mi proyecto completo y diseña la arquitectura")
    assert plan.route == "DEEP"


@pytest.mark.asyncio
async def test_deep_plan_enables_planning():
    clf = HybridIntentClassifier(ToyEmbeddings(_mapping()))
    plan = await clf.classify("Diseña un plan completo de negocio")
    assert plan.route == "DEEP"
    assert plan.needs_planning is True
    assert plan.needs_validation is True
    assert plan.needs_memory is True
