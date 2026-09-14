"""Test del rate limiting aplicado a un endpoint real.

Registramos un usuario nuevo y hacemos login repetido. El endpoint
/auth/login ya tiene RateLimit aplicado. Verificamos que devuelve 429.

NOTA: los endpoints con RateLimit usan IP del cliente. En los tests
httpx usa la misma IP (testclient). Es lo que queremos.
"""
from __future__ import annotations

import uuid

import pytest

from app.security.rate_limit import get_limiter


@pytest.fixture(autouse=True)
def _clear_limiter():
    """Limpia el contador entre tests."""
    get_limiter().reset_all()
    yield
    get_limiter().reset_all()


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429(client):
    # Registramos un usuario
    email = f"rl-{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "RL", "email": email, "password": "secreto123"},
    )
    assert r.status_code == 201
    client.cookies.clear()

    # El endpoint login tiene RateLimit("login", 5, 60)
    # Hacemos 5 intentos válidos... pero son logins exitosos, sí cuentan.
    responses = []
    for _ in range(6):
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "secreto123"},
        )
        responses.append(r.status_code)

    # Los 5 primeros deben pasar (200), el 6º debe dar 429
    assert responses[:5] == [200] * 5
    assert responses[5] == 429


@pytest.mark.asyncio
async def test_login_rate_limit_headers(client):
    """Cuando se bloquea, la respuesta incluye Retry-After."""
    email = f"rl-{uuid.uuid4().hex[:10]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"name": "RL2", "email": email, "password": "secreto123"},
    )
    client.cookies.clear()

    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "secreto123"},
        )

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secreto123"},
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert int(r.headers["Retry-After"]) > 0