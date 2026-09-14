"""Tests del Planner.

Usa un StubLLM controlado para simular respuestas del LLM (JSON válido, JSON
inválido, excepción) y verificar el comportamiento del planner en cada caso.
"""
from __future__ import annotations

import pytest

from app.core.planner import Planner
from app.core.schemas.llm import LLMResponse, TokenUsage


class StubLLM:
    name = "stub"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def generate(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        self.calls += 1
        text = self._responses.pop(0) if self._responses else ""
        return LLMResponse(text=text, usage=TokenUsage(), model="stub")

    async def stream(self, *args, **kwargs):  # pragma: no cover
        yield None

    def count_tokens(self, messages) -> int:
        return 0


class BrokenLLM:
    name = "broken"

    async def generate(self, *args, **kwargs):
        raise RuntimeError("boom")

    async def stream(self, *args, **kwargs):  # pragma: no cover
        yield None

    def count_tokens(self, messages) -> int:
        return 0


VALID_PLAN = """{
  "goal": "Diseñar un sistema de inventario",
  "steps": [
    {"id": "s1", "kind": "llm", "description": "Analizar requisitos",
     "depends_on": []},
    {"id": "s2", "kind": "llm", "description": "Diseñar esquema de BD",
     "depends_on": ["s1"]},
    {"id": "s3", "kind": "llm", "description": "Sintetizar propuesta",
     "depends_on": ["s2"]}
  ],
  "reasoning": "Descomposición en análisis, diseño y síntesis"
}"""


@pytest.mark.asyncio
async def test_valid_plan_parsed():
    p = Planner(StubLLM([VALID_PLAN]))
    plan = await p.plan("Diseña un sistema de inventario")
    assert len(plan.steps) == 3
    assert plan.steps[0].id == "s1"
    assert plan.steps[1].depends_on == ["s1"]


@pytest.mark.asyncio
async def test_plan_with_markdown_fence():
    wrapped = f"```json\n{VALID_PLAN}\n```"
    p = Planner(StubLLM([wrapped]))
    plan = await p.plan("Diseña algo")
    assert len(plan.steps) == 3


@pytest.mark.asyncio
async def test_invalid_json_triggers_retry():
    p = Planner(StubLLM(["no es json", VALID_PLAN]))
    plan = await p.plan("Diseña algo")
    assert len(plan.steps) == 3


@pytest.mark.asyncio
async def test_double_failure_degrades_to_single_llm_step():
    p = Planner(StubLLM(["basura", "más basura"]))
    plan = await p.plan("Diseña un sistema complejo")
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == "llm"
    assert "degrad" in (plan.reasoning or "").lower()


@pytest.mark.asyncio
async def test_llm_exception_degrades():
    p = Planner(BrokenLLM())
    plan = await p.plan("Diseña un sistema complejo")
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == "llm"


@pytest.mark.asyncio
async def test_max_steps_trim():
    """8 pasos pedidos, máximo 6 → recorta. El goal debe ser válido (>=3)."""
    steps = ", ".join(
        f'{{"id":"s{i}","kind":"llm","description":"paso {i}","depends_on":[]}}'
        for i in range(8)
    )
    raw = f'{{"goal":"objetivo de prueba","steps":[{steps}],"reasoning":null}}'
    p = Planner(StubLLM([raw]), max_steps=6)
    plan = await p.plan("haz algo complejo")
    assert len(plan.steps) == 6


@pytest.mark.asyncio
async def test_dangling_dependency_removed():
    """Dependencias hacia pasos inexistentes se eliminan sin romper el plan."""
    raw = """{
      "goal": "objetivo de prueba",
      "steps": [
        {"id": "s1", "kind": "llm", "description": "uno", "depends_on": []},
        {"id": "s2", "kind": "llm", "description": "dos",
         "depends_on": ["s1", "sNOPE"]}
      ],
      "reasoning": null
    }"""
    p = Planner(StubLLM([raw]))
    plan = await p.plan("haz algo")
    # sNOPE no existe → se elimina; s1 se mantiene
    assert plan.steps[1].depends_on == ["s1"]


@pytest.mark.asyncio
async def test_short_message_does_not_crash_fallback():
    """Si el mensaje es muy corto (<3 chars), el fallback no debe petar."""
    p = Planner(StubLLM(["basura", "más basura"]))
    plan = await p.plan("x")  # solo 1 carácter
    assert len(plan.steps) == 1
    # El goal queda saneado automáticamente.
    assert len(plan.goal) >= 3