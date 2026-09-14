"""Tests de los endpoints /admin.

Cubren:
  - RBAC: un USER normal no puede acceder a rutas admin.
  - ADMIN puede gestionar usuarios y ver analytics.
  - Solo SUPER_ADMIN puede eliminar usuarios y leer el audit.
  - Reglas de auto-protección (no auto-degradación, no auto-bloqueo).
  - Config dinámico (leer, actualizar, borrar override).
  - Audit logs registran las acciones.
  - Analytics y system health responden.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.role import Role
from app.db.models.user import User


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _register(client, name: str = "Tester") -> dict:
    """Registra un USER normal y devuelve headers X-Dev-User-Id."""
    email = f"adm-{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "secreto123"},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    client.cookies.clear()
    return {"X-Dev-User-Id": uid}


async def _register_admin(
    client, session: AsyncSession, role_name: str = "ADMIN"
) -> dict:
    """Registra un usuario y le asigna el rol indicado directamente en BD."""
    headers = await _register(client, name=role_name)
    uid = uuid.UUID(headers["X-Dev-User-Id"])

    role = await session.scalar(select(Role).where(Role.name == role_name))
    assert role is not None, f"rol {role_name} no existe en BD de test"

    await session.execute(
        update(User).where(User.id == uid).values(role_id=role.id)
    )
    await session.commit()
    return headers


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_admin_endpoints_require_auth(client):
    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_user_cannot_access_admin(client):
    """Un USER normal no tiene permisos admin.panel ni users.read."""
    headers = await _register(client, "Normal User")

    r = await client.get("/api/v1/admin/users", headers=headers)
    assert r.status_code == 403

    r = await client.get("/api/v1/admin/analytics/overview", headers=headers)
    assert r.status_code == 403

    r = await client.get("/api/v1/admin/config", headers=headers)
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_admin_can_list_users(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    r = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert r.status_code == 200, r.text
    users = r.json()
    assert isinstance(users, list)
    assert len(users) >= 1


@pytest.mark.asyncio
async def test_admin_can_block_and_unblock_user(
    client, session: AsyncSession
):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    target_headers = await _register(client, "Target")
    target_id = target_headers["X-Dev-User-Id"]

    r = await client.post(
        f"/api/v1/admin/users/{target_id}/block",
        json={"reason": "abuse"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "BLOCKED"

    r = await client.post(
        f"/api/v1/admin/users/{target_id}/unblock",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_admin_can_change_role(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    target_headers = await _register(client, "Future Moderator")
    target_id = target_headers["X-Dev-User-Id"]

    r = await client.patch(
        f"/api/v1/admin/users/{target_id}/role",
        json={"role": "MODERATOR"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "MODERATOR"


@pytest.mark.asyncio
async def test_admin_cannot_change_own_role(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    admin_id = admin_headers["X-Dev-User-Id"]

    r = await client.patch(
        f"/api/v1/admin/users/{admin_id}/role",
        json={"role": "USER"},
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "propio" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_cannot_block_self(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    admin_id = admin_headers["X-Dev-User-Id"]

    r = await client.post(
        f"/api/v1/admin/users/{admin_id}/block",
        json={"reason": "test"},
        headers=admin_headers,
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_admin_can_read_config(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    r = await client.get("/api/v1/admin/config", headers=admin_headers)
    assert r.status_code == 200
    items = r.json()
    keys = {i["key"] for i in items}
    assert "memory_top_k" in keys
    assert "rag_top_k" in keys


@pytest.mark.asyncio
async def test_admin_can_update_config(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    r = await client.put(
        "/api/v1/admin/config/memory_top_k",
        json={"value": 99},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key"] == "memory_top_k"
    assert body["value"] == 99
    assert body["is_override"] is True


@pytest.mark.asyncio
async def test_admin_cannot_modify_secrets(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    for key in ("openai_api_key", "secret_key", "database_url"):
        r = await client.put(
            f"/api/v1/admin/config/{key}",
            json={"value": "hacked"},
            headers=admin_headers,
        )
        assert r.status_code == 400, f"key={key} debería estar protegida"


@pytest.mark.asyncio
async def test_admin_can_delete_config_override(
    client, session: AsyncSession
):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    await client.put(
        "/api/v1/admin/config/memory_top_k",
        json={"value": 42},
        headers=admin_headers,
    )
    r = await client.delete(
        "/api/v1/admin/config/memory_top_k", headers=admin_headers
    )
    assert r.status_code == 204

    r = await client.get("/api/v1/admin/config/memory_top_k", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_override"] is False


# --------------------------------------------------------------------------- #
# Audit (solo SUPER_ADMIN)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_audit_records_admin_actions(client, session: AsyncSession):
    """Un ADMIN realiza la acción, un SUPER_ADMIN lee el audit."""
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    super_headers = await _register_admin(
        client, session, role_name="SUPER_ADMIN"
    )
    target_headers = await _register(client, "Audit Target")
    target_id = target_headers["X-Dev-User-Id"]

    await client.post(
        f"/api/v1/admin/users/{target_id}/block",
        json={"reason": "test audit"},
        headers=admin_headers,
    )

    # El SUPER_ADMIN lee el audit (ADMIN no tiene admin.audit)
    r = await client.get("/api/v1/admin/audit", headers=super_headers)
    assert r.status_code == 200
    logs = r.json()
    block_logs = [l for l in logs if l["action"] == "user.block"]
    assert len(block_logs) >= 1
    log_entry = block_logs[0]
    assert log_entry["entity_type"] == "user"
    assert log_entry["entity_id"] == target_id
    assert log_entry["before"]["status"] == "ACTIVE"
    assert log_entry["after"]["status"] == "BLOCKED"
    assert log_entry["meta"]["reason"] == "test audit"


@pytest.mark.asyncio
async def test_audit_records_config_change(client, session: AsyncSession):
    """Un ADMIN realiza el cambio de config, un SUPER_ADMIN lee el audit."""
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    super_headers = await _register_admin(
        client, session, role_name="SUPER_ADMIN"
    )

    await client.put(
        "/api/v1/admin/config/rag_top_k",
        json={"value": 12},
        headers=admin_headers,
    )

    r = await client.get(
        "/api/v1/admin/audit?action=config.update", headers=super_headers
    )
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) >= 1
    assert logs[0]["entity_id"] == "rag_top_k"


@pytest.mark.asyncio
async def test_admin_cannot_read_audit(client, session: AsyncSession):
    """ADMIN no tiene permiso admin.audit; solo SUPER_ADMIN."""
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    r = await client.get("/api/v1/admin/audit", headers=admin_headers)
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Analytics y system
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_analytics_overview(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    r = await client.get(
        "/api/v1/admin/analytics/overview", headers=admin_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["users_total"] >= 1
    assert body["users_active"] >= 1
    assert isinstance(body["tokens_total"], int)
    assert isinstance(body["cost_estimate_usd"], float)


@pytest.mark.asyncio
async def test_analytics_timeseries(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    r = await client.get(
        "/api/v1/admin/analytics/timeseries?days=7", headers=admin_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 7
    assert len(body["points"]) == 7


@pytest.mark.asyncio
async def test_system_health(client, session: AsyncSession):
    admin_headers = await _register_admin(client, session, role_name="ADMIN")

    r = await client.get("/api/v1/admin/system/health", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["env"] == "test"
    assert body["tools_count"] == 4


# --------------------------------------------------------------------------- #
# Delete user (solo SUPER_ADMIN)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_admin_cannot_delete_user(client, session: AsyncSession):
    """ADMIN no tiene permiso users.delete."""
    admin_headers = await _register_admin(client, session, role_name="ADMIN")
    target_headers = await _register(client, "Delete Target")
    target_id = target_headers["X-Dev-User-Id"]

    r = await client.delete(
        f"/api/v1/admin/users/{target_id}", headers=admin_headers
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_delete_user(client, session: AsyncSession):
    super_headers = await _register_admin(
        client, session, role_name="SUPER_ADMIN"
    )
    target_headers = await _register(client, "Delete Target")
    target_id = target_headers["X-Dev-User-Id"]

    r = await client.delete(
        f"/api/v1/admin/users/{target_id}", headers=super_headers
    )
    assert r.status_code == 204

    r = await client.get(
        f"/api/v1/admin/users/{target_id}", headers=super_headers
    )
    assert r.status_code == 200
    assert r.json()["status"] == "DELETED"