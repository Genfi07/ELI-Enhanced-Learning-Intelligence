import uuid

import pytest

from tests.conftest import ROLE_USER_ID

@pytest.mark.asyncio
async def test_create_and_list_conversations(client, dev_user):
    headers = {"X-Dev-User-Id": str(dev_user.id)}

    r = await client.post("/api/v1/conversations", json={"title": "uno"}, headers=headers)
    assert r.status_code == 201
    cid = r.json()["id"]

    r = await client.get("/api/v1/conversations", headers=headers)
    assert r.status_code == 200
    assert any(c["id"] == cid for c in r.json())


@pytest.mark.asyncio
async def test_conversations_are_isolated_per_user(client, dev_user, session):
    from app.db.models.user import User

    other = User(
        id=uuid.uuid4(),
        name="Otro",
        email=f"otro-{uuid.uuid4().hex[:8]}@eli.local",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(other)
    await session.commit()

    r = await client.post(
        "/api/v1/conversations",
        json={"title": "mía"},
        headers={"X-Dev-User-Id": str(dev_user.id)},
    )
    my_conv = r.json()["id"]

    # El otro usuario no la ve
    r = await client.get(
        "/api/v1/conversations", headers={"X-Dev-User-Id": str(other.id)}
    )
    assert all(c["id"] != my_conv for c in r.json())

    # Ni puede leer sus mensajes
    r = await client.get(
        f"/api/v1/conversations/{my_conv}/messages",
        headers={"X-Dev-User-Id": str(other.id)},
    )
    assert r.status_code == 404

    # Ni borrarla
    r = await client.delete(
        f"/api/v1/conversations/{my_conv}",
        headers={"X-Dev-User-Id": str(other.id)},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_cascades(client, dev_user):
    headers = {"X-Dev-User-Id": str(dev_user.id)}

    r = await client.post("/api/v1/conversations", json={"title": "tmp"}, headers=headers)
    cid = r.json()["id"]

    r = await client.delete(f"/api/v1/conversations/{cid}", headers=headers)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/conversations/{cid}/messages", headers=headers)
    assert r.status_code == 404