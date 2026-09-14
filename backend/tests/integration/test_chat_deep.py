"""Test end-to-end de la ruta DEEP (Planning + Execution).

Verifica que cuando el mensaje activa la ruta DEEP, el orquestador:
  1. Llama al planner con el mensaje.
  2. Emite el evento `plan_created` con los pasos.
  3. Ejecuta el plan paso a paso con el executor.
  4. Emite el evento `plan_executed` con el estado de cada paso.
  5. Inyecta el `final_context` en la síntesis final.
  6. Emite el evento `final` con `planned=True`.

Estrategia: monkeypatcheamos el `_orchestrator` del router `chat` con una
instancia que usa un LLM controlado. Así evitamos depender de un LLM real
y podemos verificar exactamente qué pasos se ejecutan.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from tests.conftest import ROLE_USER_ID


# --------------------------------------------------------------------------- #
# LLM controlado: devuelve JSON para el planner, textos para los pasos,
# y tokens para el streaming de síntesis.
# --------------------------------------------------------------------------- #
PLAN_JSON = """{
  "goal": "Analizar y proponer arquitectura",
  "steps": [
    {"id": "s1", "kind": "llm", "description": "Analizar requisitos", "depends_on": []},
    {"id": "s2", "kind": "llm", "description": "Proponer arquitectura", "depends_on": ["s1"]}
  ],
  "reasoning": "Análisis antes de propuesta"
}"""


class ScriptedLLM:
    """Proveedor de LLM programado para devolver respuestas en orden."""

    name = "scripted"

    def __init__(self, gen_responses: list[str], stream_tokens: list[str]) -> None:
        self._gen = list(gen_responses)
        self._stream = list(stream_tokens)
        self.gen_calls = 0
        self.stream_calls = 0

    async def generate(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        from app.core.schemas.llm import LLMResponse, TokenUsage

        self.gen_calls += 1
        text = self._gen.pop(0) if self._gen else ""
        return LLMResponse(text=text, usage=TokenUsage(), model="scripted")

    async def stream(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        from app.core.schemas.llm import LLMChunk, TokenUsage

        self.stream_calls += 1
        for tok in self._stream:
            yield LLMChunk(delta=tok)
        yield LLMChunk(is_final=True, usage=TokenUsage())

    def count_tokens(self, messages) -> int:
        return 0


@pytest.fixture
def scripted_orchestrator(monkeypatch):
    """Reemplaza el orquestador global del router chat por uno controlado."""
    from app.api.v1.routers import chat as chat_module
    from app.core.intent_classifier import HybridIntentClassifier
    from app.core.orchestrator import Orchestrator
    from app.core.plan_executor import PlanExecutor
    from app.core.planner import Planner
    from app.llm.embeddings_fake import FakeEmbeddingsProvider
    from app.llm.router import ModelRouter

    # El planner recibe PLAN_JSON como primera respuesta del LLM.
    # Cada paso del plan (2 en este caso) pide una generación.
    # El streaming final son los tokens de la síntesis.
    llm = ScriptedLLM(
        gen_responses=[
            PLAN_JSON,                       # planner
            "Análisis: requisitos identificados A, B, C.",  # step s1
            "Propuesta: arquitectura modular en capas.",    # step s2
        ],
        stream_tokens=["Respuesta ", "final ", "sintetizada."],
    )
    embeddings = FakeEmbeddingsProvider()
    orch = Orchestrator(
        model_router=ModelRouter(provider=llm),
        classifier=HybridIntentClassifier(embeddings=embeddings),
        planner=Planner(llm),
        executor=PlanExecutor(llm),
    )
    monkeypatch.setattr(chat_module, "_orchestrator", orch)
    return llm


async def _read_sse(response) -> list[dict]:
    events: list[dict] = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.fixture
async def deep_user(session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        name="Deep User",
        email=f"deep-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_deep_route_plans_and_executes(
    client, deep_user: User, scripted_orchestrator
):
    uid = deep_user.id
    headers = {"X-Dev-User-Id": str(uid)}

    # 1. Crear conversación
    r = await client.post(
        "/api/v1/conversations", json={"title": "deep"}, headers=headers
    )
    conv_id = r.json()["id"]

    # 2. Enviar mensaje que activa DEEP (contiene "analiza" y "diseña")
    r = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Analiza mi proyecto y diseña la arquitectura completa",
        },
        headers=headers,
    )
    assert r.status_code == 200
    events = await _read_sse(r)

    # 3. Verificar la secuencia de eventos
    types = [e["type"] for e in events]

    # meta con route=DEEP
    assert types[0] == "meta"
    assert events[0]["route"] == "DEEP"

    # plan_created con 2 pasos
    plan_created = next((e for e in events if e["type"] == "plan_created"), None)
    assert plan_created is not None, f"Eventos: {types}"
    assert plan_created["goal"] == "Analizar y proponer arquitectura"
    assert len(plan_created["steps"]) == 2
    assert plan_created["steps"][0]["id"] == "s1"
    assert plan_created["steps"][1]["id"] == "s2"

    # plan_executed con ambos pasos en estado done
    plan_executed = next((e for e in events if e["type"] == "plan_executed"), None)
    assert plan_executed is not None
    assert plan_executed["status"] == "ok"
    step_statuses = {s["id"]: s["status"] for s in plan_executed["steps"]}
    assert step_statuses == {"s1": "done", "s2": "done"}

    # tokens del streaming de síntesis
    token_text = "".join(e["delta"] for e in events if e["type"] == "token")
    assert token_text == "Respuesta final sintetizada."

    # final con planned=True y metadatos del plan
    final = events[-1]
    assert final["type"] == "final"
    assert final["planned"] is True
    assert final["plan_steps"] == 2
    assert final["plan_status"] == "ok"


@pytest.mark.asyncio
async def test_deep_llm_call_count(
    client, deep_user: User, scripted_orchestrator
):
    """Con un plan de 2 pasos, el LLM se llama 1 (plan) + 2 (pasos) veces
    en `generate`, más 1 vez en `stream` para la síntesis."""
    headers = {"X-Dev-User-Id": str(deep_user.id)}
    r = await client.post(
        "/api/v1/conversations", json={"title": "conteo"}, headers=headers
    )
    conv_id = r.json()["id"]

    await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conv_id,
            "message": "Analiza mi proyecto y diseña la arquitectura completa",
        },
        headers=headers,
    )
    # 3 generate: planner + 2 step ejecutions
    assert scripted_orchestrator.gen_calls == 3
    # 1 stream: síntesis final
    assert scripted_orchestrator.stream_calls == 1


@pytest.mark.asyncio
async def test_standard_route_does_not_plan(
    client, deep_user: User, scripted_orchestrator
):
    """Un mensaje STANDARD no debe activar planner ni executor."""
    headers = {"X-Dev-User-Id": str(deep_user.id)}
    r = await client.post(
        "/api/v1/conversations", json={"title": "standard"}, headers=headers
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
    events = await _read_sse(r)

    # No debe haber eventos de plan
    assert not any(e["type"] == "plan_created" for e in events)
    assert not any(e["type"] == "plan_executed" for e in events)

    # El evento final no lleva planned=True
    final = events[-1]
    assert final["type"] == "final"
    assert "planned" not in final or final.get("planned") is False

    # El planner/executor no se invocaron → solo 1 stream (síntesis normal)
    assert scripted_orchestrator.gen_calls == 0
    assert scripted_orchestrator.stream_calls == 1