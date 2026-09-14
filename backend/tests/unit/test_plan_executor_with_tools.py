"""Test del PlanExecutor con una tool real.

Verifica que cuando el executor recibe `tool_runtime`, `session` y `user`,
los pasos `kind=tool` invocan la herramienta real y su resultado se pasa
al siguiente paso como contexto.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plan_executor import PlanExecutor
from app.core.schemas.llm import LLMResponse, TokenUsage
from app.core.schemas.plan import ExecutionPlan, PlanStep
from app.db.models.user import User
from app.tools.registry import build_registry
from app.tools.runtime import ToolRuntime
from tests.conftest import ROLE_USER_ID


class ScriptedLLM:
    name = "scripted"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def generate(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        user_msg = next((m.content for m in messages if m.role == "user"), "")
        self.calls.append(user_msg)
        text = self._responses.pop(0) if self._responses else ""
        return LLMResponse(text=text, usage=TokenUsage(), model="scripted")

    async def stream(self, *args, **kwargs):  # pragma: no cover
        yield None

    def count_tokens(self, messages) -> int:
        return 0


@pytest.fixture
async def tool_user(session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        name="Tool User",
        email=f"tool-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
        preferences={"autonomy_level": 4},
    )
    session.add(u)
    await session.commit()
    return u


@pytest.mark.asyncio
async def test_tool_step_invokes_real_tool(session, tool_user):
    """Un paso tool invoca calculator y su resultado entra en el contexto del siguiente paso."""
    llm = ScriptedLLM(["Conclusión: el resultado fue 14."])
    executor = PlanExecutor(
        llm,
        tool_runtime=ToolRuntime(build_registry()),
    )
    plan = ExecutionPlan(
        goal="Calcular y resumir",
        steps=[
            PlanStep(
                id="s1",
                kind="tool",
                description="calcular 2+3*4",
                depends_on=[],
                tool_name="calculator",
                tool_arguments={"expression": "2 + 3 * 4"},
            ),
            PlanStep(
                id="s2",
                kind="llm",
                description="resumir el resultado",
                depends_on=["s1"],
            ),
        ],
    )

    result = await executor.execute(
        plan,
        user_message="calcula 2+3*4 y dime el resultado",
        session=session,
        user=tool_user,
        conversation_id=None,
    )

    assert result.status == "ok"
    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["s1"] == "done"
    assert statuses["s2"] == "done"

    # El output del paso s1 debe contener el resultado 14
    s1_result = next(r for r in result.step_results if r.step_id == "s1")
    assert s1_result.output is not None
    assert "14" in s1_result.output

    # El LLM del paso s2 debe haber visto el output del paso s1
    assert "14" in llm.calls[0]


@pytest.mark.asyncio
async def test_tool_step_fails_propagates(session, tool_user):
    """Si la tool falla, el paso queda failed y sus dependientes se saltan."""
    llm = ScriptedLLM(["no debería ejecutarse"])
    executor = PlanExecutor(
        llm,
        tool_runtime=ToolRuntime(build_registry()),
    )
    plan = ExecutionPlan(
        goal="Objetivo de prueba",
        steps=[
            PlanStep(
                id="s1",
                kind="tool",
                description="expresión inválida",
                depends_on=[],
                tool_name="calculator",
                tool_arguments={"expression": "import os"},
            ),
            PlanStep(
                id="s2",
                kind="llm",
                description="resumir el fallo",
                depends_on=["s1"],
            ),
        ],
    )

    result = await executor.execute(
        plan,
        user_message="x",
        session=session,
        user=tool_user,
        conversation_id=None,
    )
    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["s1"] == "failed"
    assert statuses["s2"] == "skipped"


@pytest.mark.asyncio
async def test_tool_step_unknown_falls_to_stub(session, tool_user):
    """Sin tool_runtime, los pasos tool se comportan como stub."""
    llm = ScriptedLLM(["resumen directo"])
    executor = PlanExecutor(llm)  # sin tool_runtime

    plan = ExecutionPlan(
        goal="Objetivo de prueba",
        steps=[
            PlanStep(
                id="s1",
                kind="tool",
                description="usar herramienta",
                depends_on=[],
                tool_name="calculator",
                tool_arguments={"expression": "1+1"},
            ),
            PlanStep(
                id="s2",
                kind="llm",
                description="resumir",
                depends_on=["s1"],
            ),
        ],
    )

    result = await executor.execute(plan, user_message="x")
    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["s1"] == "skipped"
    assert statuses["s2"] == "done"