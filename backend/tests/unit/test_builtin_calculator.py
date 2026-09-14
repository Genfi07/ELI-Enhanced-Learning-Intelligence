"""Tests de la tool calculator."""
from __future__ import annotations

import uuid

import pytest

from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.tools.builtin.calculator import CalculatorTool


@pytest.fixture
def calc() -> CalculatorTool:
    return CalculatorTool()


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(
        user_id=uuid.uuid4(),
        conversation_id=None,
        autonomy_level=2,
    )


# --------------------------------------------------------------------------- #
# Casos válidos
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_basic_sum(calc, ctx):
    res = await calc.execute({"expression": "2 + 3"}, ctx)
    assert res["result"] == 5


@pytest.mark.asyncio
async def test_operator_precedence(calc, ctx):
    res = await calc.execute({"expression": "2 + 3 * 4"}, ctx)
    assert res["result"] == 14


@pytest.mark.asyncio
async def test_parentheses(calc, ctx):
    res = await calc.execute({"expression": "(2 + 3) * 4"}, ctx)
    assert res["result"] == 20


@pytest.mark.asyncio
async def test_floor_div_and_mod(calc, ctx):
    assert (await calc.execute({"expression": "7 // 2"}, ctx))["result"] == 3
    assert (await calc.execute({"expression": "7 % 3"}, ctx))["result"] == 1


@pytest.mark.asyncio
async def test_power(calc, ctx):
    res = await calc.execute({"expression": "2 ** 10"}, ctx)
    assert res["result"] == 1024


@pytest.mark.asyncio
async def test_unary_minus(calc, ctx):
    res = await calc.execute({"expression": "-5 + 3"}, ctx)
    assert res["result"] == -2


@pytest.mark.asyncio
async def test_function_abs(calc, ctx):
    res = await calc.execute({"expression": "abs(-7)"}, ctx)
    assert res["result"] == 7


@pytest.mark.asyncio
async def test_function_round(calc, ctx):
    res = await calc.execute({"expression": "round(3.7)"}, ctx)
    assert res["result"] == 4


@pytest.mark.asyncio
async def test_function_min_max(calc, ctx):
    assert (await calc.execute({"expression": "min(3, 5, 1)"}, ctx))["result"] == 1
    assert (await calc.execute({"expression": "max(3, 5, 1)"}, ctx))["result"] == 5


@pytest.mark.asyncio
async def test_constant_pi(calc, ctx):
    res = await calc.execute({"expression": "pi"}, ctx)
    assert abs(res["result"] - 3.14159265) < 1e-6


@pytest.mark.asyncio
async def test_constant_e_used(calc, ctx):
    res = await calc.execute({"expression": "round(e * 100)"}, ctx)
    # e * 100 ≈ 271.828
    assert res["result"] == 272


# --------------------------------------------------------------------------- #
# Rechazos
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_rejects_empty(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": ""}, ctx)


@pytest.mark.asyncio
async def test_rejects_non_string(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": 5}, ctx)


@pytest.mark.asyncio
async def test_rejects_attribute_access(calc, ctx):
    # Intento de (1).__class__.__mro__ — escape clásico
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "(1).__class__"}, ctx)


@pytest.mark.asyncio
async def test_rejects_unknown_function(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "eval('1+1')"}, ctx)


@pytest.mark.asyncio
async def test_rejects_unknown_name(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "foo + 1"}, ctx)


@pytest.mark.asyncio
async def test_rejects_huge_exponent(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "9 ** 100000"}, ctx)


@pytest.mark.asyncio
async def test_rejects_comprehension(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "[x for x in range(10)]"}, ctx)


@pytest.mark.asyncio
async def test_rejects_lambda(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "(lambda: 1)()"}, ctx)


@pytest.mark.asyncio
async def test_rejects_boolean(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "True + 1"}, ctx)


@pytest.mark.asyncio
async def test_rejects_too_long(calc, ctx):
    with pytest.raises(ToolExecutionError):
        await calc.execute({"expression": "1+" * 500 + "1"}, ctx)