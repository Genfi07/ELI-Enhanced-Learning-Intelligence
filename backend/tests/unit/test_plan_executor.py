"""Tests del PlanExecutor.

StubLLM controlado para verificar:
  - Ejecución en orden topológico.
  - Política de errores (failed propaga, skipped no bloquea).
  - Stubs de fases futuras (tool/rag/memory) devuelven skipped sin romper.
  - Estado global (ok / partial / failed).
  - Presupuesto de chars en final_context (los que no caben se saltan,
    no abortan el resto).
"""
from __future__ import annotations

import pytest

from app.core.plan_executor import PlanExecutor, _topological_order
from app.core.schemas.llm import LLMResponse, TokenUsage
from app.core.schemas.plan import ExecutionPlan, PlanStep


class ScriptedLLM:
    """LLM que devuelve respuestas predefinidas en orden."""

    name = "scripted"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def generate(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        user_msg = next(
            (m.content for m in messages if m.role == "user"), ""
        )
        self.calls.append(user_msg)
        text = self._responses.pop(0) if self._responses else ""
        return LLMResponse(text=text, usage=TokenUsage(), model="scripted")

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


def _plan(steps: list[dict], goal: str = "Objetivo de prueba") -> ExecutionPlan:
    return ExecutionPlan(goal=goal, steps=[PlanStep(**s) for s in steps])


# --------------------------------------------------------------------------- #
# Topological sort
# --------------------------------------------------------------------------- #
def test_topological_order_respects_deps():
    plan = _plan([
        {"id": "s3", "kind": "llm", "description": "tercero", "depends_on": ["s2"]},
        {"id": "s1", "kind": "llm", "description": "primero", "depends_on": []},
        {"id": "s2", "kind": "llm", "description": "segundo", "depends_on": ["s1"]},
    ])
    ordered = _topological_order(plan.steps)
    ids = [s.id for s in ordered]
    assert ids.index("s1") < ids.index("s2") < ids.index("s3")


# --------------------------------------------------------------------------- #
# Ejecución básica
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executes_llm_steps_in_order():
    llm = ScriptedLLM(["análisis uno", "análisis dos"])
    ex = PlanExecutor(llm)
    plan = _plan([
        {"id": "s1", "kind": "llm", "description": "analizar", "depends_on": []},
        {"id": "s2", "kind": "llm", "description": "sintetizar", "depends_on": ["s1"]},
    ])
    result = await ex.execute(plan, user_message="ayúdame con X")
    assert result.status == "ok"
    assert [r.status for r in result.step_results] == ["done", "done"]
    # El segundo paso debe incluir el output del primero en su prompt
    assert "análisis uno" in llm.calls[1]


@pytest.mark.asyncio
async def test_partial_when_some_step_fails():
    llm = ScriptedLLM(["bueno uno", "", "bueno tres"])
    ex = PlanExecutor(llm)
    plan = _plan([
        {"id": "s1", "kind": "llm", "description": "uno", "depends_on": []},
        {"id": "s2", "kind": "llm", "description": "dos", "depends_on": []},
        {"id": "s3", "kind": "llm", "description": "tres", "depends_on": []},
    ])
    result = await ex.execute(plan, user_message="x")
    assert result.status == "partial"
    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["s1"] == "done"
    assert statuses["s2"] == "failed"   # respuesta vacía
    assert statuses["s3"] == "done"


@pytest.mark.asyncio
async def test_failed_step_skips_dependents():
    llm = ScriptedLLM([""])
    ex = PlanExecutor(llm)
    plan = _plan([
        {"id": "s1", "kind": "llm", "description": "falla", "depends_on": []},
        {"id": "s2", "kind": "llm", "description": "depende", "depends_on": ["s1"]},
    ])
    result = await ex.execute(plan, user_message="x")
    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["s1"] == "failed"
    assert statuses["s2"] == "skipped"
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_skipped_stub_does_not_block_dependents():
    """Un step `tool` es un stub, pero no impide que los pasos siguientes corran."""
    llm = ScriptedLLM(["conclusión"])
    ex = PlanExecutor(llm)
    plan = _plan([
        {"id": "s1", "kind": "tool", "description": "usar herramienta",
         "depends_on": [], "tool_name": "calculator"},
        {"id": "s2", "kind": "llm", "description": "concluir", "depends_on": ["s1"]},
    ])
    result = await ex.execute(plan, user_message="x")
    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["s1"] == "skipped"
    assert statuses["s2"] == "done"
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_all_stubs_returns_failed():
    ex = PlanExecutor(ScriptedLLM([]))
    plan = _plan([
        {"id": "s1", "kind": "rag", "description": "buscar en docs", "depends_on": []},
        {"id": "s2", "kind": "tool", "description": "usar tool", "depends_on": []},
    ])
    result = await ex.execute(plan, user_message="x")
    assert all(r.status == "skipped" and r.is_stub for r in result.step_results)
    assert result.status == "failed"  # ningún paso útil → failed


@pytest.mark.asyncio
async def test_llm_exception_marks_step_failed():
    ex = PlanExecutor(BrokenLLM())
    plan = _plan([
        {"id": "s1", "kind": "llm", "description": "paso único", "depends_on": []},
    ])
    result = await ex.execute(plan, user_message="consulta")
    assert result.step_results[0].status == "failed"
    assert "boom" in (result.step_results[0].error or "")


@pytest.mark.asyncio
async def test_final_context_accumulates_outputs():
    llm = ScriptedLLM(["AAA", "BBB", "CCC"])
    ex = PlanExecutor(llm)
    plan = _plan([
        {"id": "s1", "kind": "llm", "description": "uno", "depends_on": []},
        {"id": "s2", "kind": "llm", "description": "dos", "depends_on": []},
        {"id": "s3", "kind": "llm", "description": "tres", "depends_on": []},
    ])
    result = await ex.execute(plan, user_message="x")
    assert "AAA" in result.final_context
    assert "BBB" in result.final_context
    assert "CCC" in result.final_context


@pytest.mark.asyncio
async def test_final_context_skips_oversized_but_keeps_small():
    """Un paso que no cabe se salta, pero los siguientes pequeños sí entran."""
    llm = ScriptedLLM(["X" * 100, "Y" * 5000, "Z" * 100])
    ex = PlanExecutor(llm, final_context_chars=500)
    plan = _plan([
        {"id": "s1", "kind": "llm", "description": "uno", "depends_on": []},
        {"id": "s2", "kind": "llm", "description": "dos", "depends_on": []},
        {"id": "s3", "kind": "llm", "description": "tres", "depends_on": []},
    ])
    result = await ex.execute(plan, user_message="consulta")
    # Presupuesto total respetado
    assert len(result.final_context) <= 500
    # El primer paso (100 chars) entra
    assert "XXXX" in result.final_context
    # El segundo (5000 chars) no cabe → se salta
    assert "YYYY" not in result.final_context
    # El tercero (100 chars) SÍ entra: el bloque anterior no abortó el resto
    assert "ZZZZ" in result.final_context