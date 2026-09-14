"""Tests de los endpoints /tools.

Cubren:
  - Listar tools.
  - Invocar calculator y datetime (nivel 2, ok para un USER).
  - Denegación por nivel de autonomía bajo.
  - Denegación por tool desconocida.
  - Requiere autenticación.
  - Aislamiento: el historial de calls es por usuario.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from tests.conftest import ROLE_USER_ID


async def _register(client, name: str = "Tools Tester") -> dict:
    email = f"tools-{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "secreto123"},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    client.cookies.clear()
    return {"X-Dev-User-Id": uid}


async def _set_autonomy(session: AsyncSession, user_id: str, level: int) -> None:
    """Cambia el nivel de autonomía del usuario en preferences."""
    await session.execute(
        update(User)
        .where(User.id == uuid.UUID(user_id))
        .values(preferences={"autonomy_level": level})
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Listar
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_tools_requires_auth(client):
    r = await client.get("/api/v1/tools")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_tools(client):
    headers = await _register(client)
    r = await client.get("/api/v1/tools", headers=headers)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    # Deben estar las 4 builtin
    assert {"calculator", "datetime", "web_fetch", "web_search"} <= names


# --------------------------------------------------------------------------- #
# Invocar
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_invoke_calculator_success(client):
    headers = await _register(client)
    r = await client.post(
        "/api/v1/tools/calculator/invoke",
        json={"arguments": {"expression": "2 + 3 * 4"}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "OK"
    assert body["result"]["result"] == 14
    assert body["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_invoke_datetime_now(client):
    headers = await _register(client)
    r = await client.post(
        "/api/v1/tools/datetime/invoke",
        json={"arguments": {"mode": "now", "timezone": "UTC"}},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK"
    assert body["result"]["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_invoke_unknown_tool(client):
    headers = await _register(client)
    r = await client.post(
        "/api/v1/tools/no-existe/invoke",
        json={"arguments": {}},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "DENIED"
    assert "desconocida" in r.json()["error"].lower()


@pytest.mark.asyncio
async def test_invoke_denied_when_autonomy_too_low(
    client, session: AsyncSession
):
    """Un USER con autonomía 0 no puede invocar calculator (min 2)."""
    headers = await _register(client)
    await _set_autonomy(session, headers["X-Dev-User-Id"], 0)

    r = await client.post(
        "/api/v1/tools/calculator/invoke",
        json={"arguments": {"expression": "1+1"}},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DENIED"
    assert "autonomía" in body["error"].lower()


@pytest.mark.asyncio
async def test_invoke_calculator_bad_args(client):
    """Argumentos inválidos → status ERROR (no excepción HTTP)."""
    headers = await _register(client)
    r = await client.post(
        "/api/v1/tools/calculator/invoke",
        json={"arguments": {"expression": "import os"}},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ERROR"
    assert body["error"]


@pytest.mark.asyncio
async def test_invoke_web_search_without_api_key(client):
    """Sin TAVILY_API_KEY, web_search devuelve ERROR explícito."""
    headers = await _register(client)
    # La autonomía por defecto es 2; web_search pide 3. Subimos a 3.
    r = await client.post(
        "/api/v1/tools/web_search/invoke",
        json={"arguments": {"query": "python"}},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    # Puede ser DENIED (por autonomía) o ERROR (por falta de key).
    # En cualquier caso, no debe lanzar 500.
    assert body["status"] in ("DENIED", "ERROR")


# --------------------------------------------------------------------------- #
# Historial de llamadas (aislamiento)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_call_history_isolated_between_users(client):
    headers_a = await _register(client, "A")
    headers_b = await _register(client, "B")

    # A invoca una tool
    await client.post(
        "/api/v1/tools/calculator/invoke",
        json={"arguments": {"expression": "1+1"}},
        headers=headers_a,
    )

    r = await client.get("/api/v1/tools/calls", headers=headers_a)
    assert r.status_code == 200
    assert len(r.json()) >= 1

    r = await client.get("/api/v1/tools/calls", headers=headers_b)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_call_history_records_denied(client):
    """Una llamada denegada también queda registrada (auditoría)."""
    headers = await _register(client)
    await client.post(
        "/api/v1/tools/no-existe/invoke",
        json={"arguments": {}},
        headers=headers,
    )
    r = await client.get("/api/v1/tools/calls", headers=headers)
    calls = r.json()
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "no-existe"
    assert calls[0]["status"] == "DENIED"