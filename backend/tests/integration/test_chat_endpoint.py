import json

import pytest

from tests.conftest import ROLE_USER_ID

async def _read_sse(response) -> list[dict]:
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.asyncio
async def test_chat_fast_route_end_to_end(client, dev_user):
    headers = {"X-Dev-User-Id": str(dev_user.id)}

    # 1. Crear conversación
    r = await client.post(
        "/api/v1/conversations", json={"title": "prueba"}, headers=headers
    )
    assert r.status_code == 201, r.text
    conv_id = r.json()["id"]

    # 2. Enviar mensaje FAST
    r = await client.post(
        "/api/v1/chat",
        json={"conversation_id": conv_id, "message": "Hola ELI"},
        headers=headers,
    )
    assert r.status_code == 200
    events = await _read_sse(r)

    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert "token" in types
    assert types[-1] == "final"

    meta = events[0]
    assert meta["route"] == "FAST"
    assert meta["conversation_id"] == conv_id

    final = events[-1]
    assert final["usage"]["total_tokens"] > 0

    # 3. Los mensajes quedan persistidos
    r = await client.get(
        f"/api/v1/conversations/{conv_id}/messages", headers=headers
    )
    assert r.status_code == 200
    msgs = r.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "Hola ELI"


@pytest.mark.asyncio
async def test_chat_creates_conversation_when_missing(client, dev_user):
    headers = {"X-Dev-User-Id": str(dev_user.id)}

    r = await client.post(
        "/api/v1/chat",
        json={"conversation_id": None, "message": "Hola sin conversación"},
        headers=headers,
    )
    assert r.status_code == 200
    events = await _read_sse(r)
    conv_id = events[0]["conversation_id"]

    r = await client.get("/api/v1/conversations", headers=headers)
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert conv_id in ids


@pytest.mark.asyncio
async def test_chat_rejects_foreign_conversation(client, dev_user, session):
    import uuid as _uuid
    from app.db.models.user import User

    other = User(
        id=_uuid.uuid4(),
        name="Otro",
        email=f"otro-{_uuid.uuid4().hex[:8]}@eli.local",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(other)
    await session.commit()

    # Creamos conversación como 'other'
    r = await client.post(
        "/api/v1/conversations",
        json={"title": "privada"},
        headers={"X-Dev-User-Id": str(other.id)},
    )
    foreign_conv = r.json()["id"]

    # dev_user intenta usarla
    r = await client.post(
        "/api/v1/chat",
        json={"conversation_id": foreign_conv, "message": "intruso"},
        headers={"X-Dev-User-Id": str(dev_user.id)},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_chat_requires_auth_header(client):
    r = await client.post("/api/v1/chat", json={"message": "hola"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_chat_rejects_empty_message(client, dev_user):
    headers = {"X-Dev-User-Id": str(dev_user.id)}
    r = await client.post("/api/v1/chat", json={"message": "   "}, headers=headers)
    assert r.status_code == 400