"""Tests de la tool datetime."""
from __future__ import annotations

import uuid

import pytest

from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.tools.builtin.datetime_tool import DatetimeTool


@pytest.fixture
def dt() -> DatetimeTool:
    return DatetimeTool()


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(
        user_id=uuid.uuid4(),
        conversation_id=None,
        autonomy_level=2,
    )


# --------------------------------------------------------------------------- #
# mode=now
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_now_utc(dt, ctx):
    res = await dt.execute({"mode": "now"}, ctx)
    assert "iso" in res
    assert "unix" in res
    assert res["timezone"] == "UTC"
    assert isinstance(res["unix"], int)


@pytest.mark.asyncio
async def test_now_madrid(dt, ctx):
    res = await dt.execute({"mode": "now", "timezone": "Europe/Madrid"}, ctx)
    assert res["timezone"] == "Europe/Madrid"


@pytest.mark.asyncio
async def test_now_invalid_timezone(dt, ctx):
    with pytest.raises(ToolExecutionError):
        await dt.execute({"mode": "now", "timezone": "Fake/Zone"}, ctx)


# --------------------------------------------------------------------------- #
# mode=diff
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_diff_between_dates(dt, ctx):
    res = await dt.execute(
        {
            "mode": "diff",
            "date_a": "2026-01-01T00:00:00Z",
            "date_b": "2026-01-02T00:00:00Z",
        },
        ctx,
    )
    assert res["seconds"] == 86400
    assert res["days"] == 1
    assert "después" in res["human"]


@pytest.mark.asyncio
async def test_diff_negative(dt, ctx):
    res = await dt.execute(
        {
            "mode": "diff",
            "date_a": "2026-01-02T00:00:00Z",
            "date_b": "2026-01-01T00:00:00Z",
        },
        ctx,
    )
    assert res["seconds"] == -86400
    assert "antes" in res["human"]


@pytest.mark.asyncio
async def test_diff_missing_date(dt, ctx):
    with pytest.raises(ToolExecutionError):
        await dt.execute({"mode": "diff", "date_a": "2026-01-01T00:00:00Z"}, ctx)


# --------------------------------------------------------------------------- #
# mode=add
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_add_days(dt, ctx):
    res = await dt.execute(
        {
            "mode": "add",
            "base": "2026-01-01T00:00:00Z",
            "days": 3,
        },
        ctx,
    )
    assert res["iso"].startswith("2026-01-04")


@pytest.mark.asyncio
async def test_add_multiple_units(dt, ctx):
    res = await dt.execute(
        {
            "mode": "add",
            "base": "2026-01-01T00:00:00Z",
            "days": 1,
            "hours": 2,
            "minutes": 30,
        },
        ctx,
    )
    assert res["iso"].startswith("2026-01-02T02:30")


@pytest.mark.asyncio
async def test_add_invalid_base(dt, ctx):
    with pytest.raises(ToolExecutionError):
        await dt.execute({"mode": "add", "base": "no-es-fecha", "days": 1}, ctx)


# --------------------------------------------------------------------------- #
# Validación general
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_invalid_mode(dt, ctx):
    with pytest.raises(ToolExecutionError):
        await dt.execute({"mode": "otro"}, ctx)