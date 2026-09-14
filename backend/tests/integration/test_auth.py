"""Tests de autenticación con email/contraseña.

Cubren el flujo completo: registro, login, /me, logout, y casos de error.
Las cookies se manejan automáticamente por httpx.AsyncClient, así que un
login dentro de un test afecta solo a ese test (el fixture `client` es
function-scoped).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ROLE_USER_ID


def _fresh_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_register_success(client):
    email = _fresh_email()
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Test User", "email": email, "password": "secreto123"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == email
    assert body["role"] == "USER"
    assert body["status"] == "ACTIVE"

    # La cookie se estableció
    assert "eli_session" in client.cookies

    # /me funciona con esa cookie
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == email


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    email = _fresh_email()
    payload = {"name": "A", "email": email, "password": "secreto123"}

    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201

    # Segundo registro con el mismo email → 409
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "X", "email": "no-es-email", "password": "secreto123"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_short_password(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "X", "email": _fresh_email(), "password": "corta"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_ignores_capitalization(client):
    """El email se guarda y se compara en minúsculas."""
    email = _fresh_email().upper()
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "X", "email": email, "password": "secreto123"},
    )
    assert r.status_code == 201
    assert r.json()["email"] == email.lower()


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_login_success(client):
    email = _fresh_email()
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Test", "email": email, "password": "secreto123"},
    )
    # Limpiar cookies del registro
    client.cookies.clear()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secreto123"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == email
    assert "eli_session" in client.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    email = _fresh_email()
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Test", "email": email, "password": "secreto123"},
    )
    client.cookies.clear()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "otra-cosa"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": _fresh_email(), "password": "secreto123"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_blocked_user(client, session: AsyncSession):
    email = _fresh_email()
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Test", "email": email, "password": "secreto123"},
    )
    user_id = r.json()["id"]

    # Bloquear al usuario manualmente
    from sqlalchemy import update
    from app.db.models.user import User

    await session.execute(
        update(User).where(User.id == uuid.UUID(user_id)).values(status="BLOCKED")
    )
    await session.commit()
    client.cookies.clear()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secreto123"},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# /me y logout
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_me_without_cookie(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_server_side(client):
    email = _fresh_email()
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Test", "email": email, "password": "secreto123"},
    )
    # Guardamos la cookie antes del logout
    cookie_before = dict(client.cookies)

    # /me funciona
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200

    # Logout
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204

    # Aunque "reinyectamos" la cookie antigua, el servidor la rechaza
    # porque la sesión está revocada en BD.
    client.cookies.update(cookie_before)
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Aislamiento
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_two_users_have_isolated_sessions(client):
    """Dos usuarios distintos con cookies distintas no se pisan."""
    email_a = _fresh_email()
    email_b = _fresh_email()

    # Registramos A y guardamos su cookie
    await client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": email_a, "password": "secreto123"},
    )
    cookie_a = dict(client.cookies)

    # Registramos B en un cliente limpio
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/register",
        json={"name": "B", "email": email_b, "password": "secreto123"},
    )
    cookie_b = dict(client.cookies)

    # /me con cookie A devuelve A
    client.cookies.clear()
    client.cookies.update(cookie_a)
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == email_a

    # /me con cookie B devuelve B
    client.cookies.clear()
    client.cookies.update(cookie_b)
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == email_b