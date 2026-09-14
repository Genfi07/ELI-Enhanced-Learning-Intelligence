"""Tests de los endpoints /memory.

Cubren:
  - Listar, crear, obtener, actualizar, borrar, historial.
  - Aislamiento entre usuarios (IDOR).
  - Soft-delete (el registro queda pero invisible).
  - El historial refleja los cambios.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from tests.conftest import ROLE_USER_ID


async def _register_and_get_headers(client, name: str = "Memory Tester") -> dict:
    """Registra un usuario y devuelve los headers con X-Dev-User-Id.

    Como estamos en env=test, el header X-Dev-User-Id funciona directamente.
    Para obtener un user_id nuevo, usamos el endpoint de registro.
    """
    email = f"mem-{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "secreto123"},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    # Limpiamos cookies para no arrastrar la sesión del registro
    client.cookies.clear()
    return {"X-Dev-User-Id": uid}


@pytest.mark.asyncio
async def test_list_empty(client):
    headers = await _register_and_get_headers(client)
    r = await client.get("/api/v1/memory", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_and_list(client):
    headers = await _register_and_get_headers(client)
    r = await client.post(
        "/api/v1/memory",
        json={
            "type": "FACT",
            "content": "El usuario trabaja en finanzas",
            "importance": 0.8,
            "confidence": 0.9,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert r.json()["source"] == "EXPLICIT"
    assert r.json()["status"] == "ACTIVE"

    r = await client.get("/api/v1/memory", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == mid


@pytest.mark.asyncio
async def test_get_by_id(client):
    headers = await _register_and_get_headers(client)
    r = await client.post(
        "/api/v1/memory",
        json={"type": "GOAL", "content": "Está aprendiendo Rust"},
        headers=headers,
    )
    mid = r.json()["id"]

    r = await client.get(f"/api/v1/memory/{mid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == mid


@pytest.mark.asyncio
async def test_update_content_regenerates(client):
    headers = await _register_and_get_headers(client)
    r = await client.post(
        "/api/v1/memory",
        json={"type": "FACT", "content": "Vive en Madrid"},
        headers=headers,
    )
    mid = r.json()["id"]

    r = await client.patch(
        f"/api/v1/memory/{mid}",
        json={"content": "Vive en Barcelona", "importance": 0.9},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == "Vive en Barcelona"
    assert body["importance"] == 0.9


@pytest.mark.asyncio
async def test_delete_is_soft(client):
    headers = await _register_and_get_headers(client)
    r = await client.post(
        "/api/v1/memory",
        json={"type": "FACT", "content": "Algo que voy a borrar"},
        headers=headers,
    )
    mid = r.json()["id"]

    r = await client.delete(f"/api/v1/memory/{mid}", headers=headers)
    assert r.status_code == 204

    # Ya no aparece en el listado activo
    r = await client.get("/api/v1/memory", headers=headers)
    assert r.json() == []

    # Pero sigue accesible si pedimos el detalle (status DELETED)
    r = await client.get(f"/api/v1/memory/{mid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "DELETED"

    # Y si filtramos por status=DELETED, aparece
    r = await client.get("/api/v1/memory?status=DELETED", headers=headers)
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_history_reflects_changes(client):
    headers = await _register_and_get_headers(client)
    r = await client.post(
        "/api/v1/memory",
        json={"type": "FACT", "content": "Contenido original"},
        headers=headers,
    )
    mid = r.json()["id"]

    await client.patch(
        f"/api/v1/memory/{mid}", json={"content": "Contenido nuevo"}, headers=headers
    )
    await client.delete(f"/api/v1/memory/{mid}", headers=headers)

    r = await client.get(f"/api/v1/memory/{mid}/history", headers=headers)
    assert r.status_code == 200
    events = r.json()
    kinds = [e["event"] for e in events]
    assert "CREATED" in kinds
    assert "UPDATED" in kinds
    assert "DELETED" in kinds


@pytest.mark.asyncio
async def test_filter_by_type(client):
    headers = await _register_and_get_headers(client)
    await client.post(
        "/api/v1/memory",
        json={"type": "FACT", "content": "Algo factual aquí"},
        headers=headers,
    )
    await client.post(
        "/api/v1/memory",
        json={"type": "PREFERENCE", "content": "Prefiere respuestas cortas"},
        headers=headers,
    )

    r = await client.get("/api/v1/memory?type=FACT", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["type"] == "FACT"


# --------------------------------------------------------------------------- #
# Aislamiento entre usuarios (IDOR)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_isolated_between_users(client):
    headers_a = await _register_and_get_headers(client, name="A")
    headers_b = await _register_and_get_headers(client, name="B")

    # A crea una memoria
    r = await client.post(
        "/api/v1/memory",
        json={"type": "FACT", "content": "Secreto de A"},
        headers=headers_a,
    )
    mid = r.json()["id"]

    # B no la ve en su listado
    r = await client.get("/api/v1/memory", headers=headers_b)
    assert r.json() == []

    # B no puede leerla por id
    r = await client.get(f"/api/v1/memory/{mid}", headers=headers_b)
    assert r.status_code == 404

    # B no puede actualizarla
    r = await client.patch(
        f"/api/v1/memory/{mid}", json={"content": "Hackeado"}, headers=headers_b
    )
    assert r.status_code == 404

    # B no puede borrarla
    r = await client.delete(f"/api/v1/memory/{mid}", headers=headers_b)
    assert r.status_code == 404

    # B no puede leer el historial
    r = await client.get(f"/api/v1/memory/{mid}/history", headers=headers_b)
    assert r.status_code == 404

    # A sigue viendo la suya
    r = await client.get(f"/api/v1/memory/{mid}", headers=headers_a)
    assert r.status_code == 200
    assert r.json()["content"] == "Secreto de A"


@pytest.mark.asyncio
async def test_requires_auth(client):
    r = await client.get("/api/v1/memory")
    assert r.status_code == 401