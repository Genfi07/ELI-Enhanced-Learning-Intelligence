"""Tests de Google OAuth con el intercambio de red mockeado.

Probamos la lógica de negocio:
  - Vinculación y creación de usuarios.
  - Reutilización de cuentas existentes.
  - Idempotencia.
  - Normalización de email.
  - Comportamiento sin credenciales configuradas.

No probamos el redirect real a Google (requiere credenciales y navegador).
Eso se valida una sola vez cuando se configuren las credenciales reales.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oauth_google import link_or_create_google_user
from app.db.models.oauth import OAuthAccount
from app.db.models.user import User
from tests.conftest import ROLE_USER_ID


# --------------------------------------------------------------------------- #
# Lógica de vinculación (función pura, sin red)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_google_creates_new_user(session: AsyncSession):
    email = f"g-{uuid.uuid4().hex[:8]}@example.com"
    user = await link_or_create_google_user(
        session,
        provider_user_id=f"sub-{uuid.uuid4().hex[:8]}",
        email=email,
        name="Usuario Google",
        picture="https://example.com/pic.jpg",
    )
    await session.commit()

    assert user.email == email
    assert user.role_id == ROLE_USER_ID
    assert user.password_hash is None
    assert user.status == "ACTIVE"
    assert user.profile_image_url == "https://example.com/pic.jpg"


@pytest.mark.asyncio
async def test_google_links_to_existing_email(session: AsyncSession):
    """Si el email ya existe como usuario local, se vincula la cuenta de Google."""
    email = f"g-{uuid.uuid4().hex[:8]}@example.com"

    # Usuario local con ese email
    existing = User(
        name="Local User",
        email=email,
        password_hash="$argon2id$fake",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(existing)
    await session.commit()

    user = await link_or_create_google_user(
        session,
        provider_user_id=f"sub-{uuid.uuid4().hex[:8]}",
        email=email,
        name="Desde Google",
        picture=None,
    )
    await session.commit()

    # Mismo usuario, no uno nuevo
    assert user.id == existing.id
    # La contraseña local se conserva (ahora puede entrar por ambos métodos)
    assert user.password_hash == "$argon2id$fake"


@pytest.mark.asyncio
async def test_google_idempotent_when_already_linked(session: AsyncSession):
    """Si el (google, sub) ya está vinculado, devuelve el mismo usuario."""
    email = f"g-{uuid.uuid4().hex[:8]}@example.com"
    sub = f"sub-{uuid.uuid4().hex[:8]}"

    user1 = await link_or_create_google_user(
        session, provider_user_id=sub, email=email, name="A", picture=None
    )
    await session.commit()

    user2 = await link_or_create_google_user(
        session, provider_user_id=sub, email=email, name="A", picture=None
    )
    await session.commit()

    assert user1.id == user2.id

    # Solo hay una vinculación
    stmt = select(OAuthAccount).where(OAuthAccount.provider_user_id == sub)
    links = list((await session.scalars(stmt)).all())
    assert len(links) == 1


@pytest.mark.asyncio
async def test_google_email_normalized_lowercase(session: AsyncSession):
    email = f"G-{uuid.uuid4().hex[:8]}@EXAMPLE.COM"
    user = await link_or_create_google_user(
        session,
        provider_user_id=f"sub-{uuid.uuid4().hex[:8]}",
        email=email,
        name="X",
        picture=None,
    )
    await session.commit()
    assert user.email == email.lower()


# --------------------------------------------------------------------------- #
# Endpoint: comportamiento sin credenciales
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_google_start_returns_503_without_config(client):
    """Sin Client ID/Secret configurados, /auth/google/start debe devolver 503."""
    r = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert r.status_code == 503
    assert "no configurado" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_google_callback_returns_503_without_config(client):
    r = await client.get("/api/v1/auth/google/callback?code=x&state=y")
    assert r.status_code == 503