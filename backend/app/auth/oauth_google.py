"""Integración con Google OAuth (OpenID Connect).

Diseño:
  - Authlib maneja el redirect y el intercambio de code → token.
  - La lógica de "qué hacer con el userinfo de Google" está AISLADA en
    `link_or_create_google_user`, que es una función pura (recibe datos,
    toca BD, no hace red). Esto permite testearla sin mockear Authlib.
  - El único punto que habla con Google es `exchange_code_for_userinfo`.
    En tests se monkeypatchea esa función y se prueba el resto del flujo.
"""
from __future__ import annotations

import uuid
from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models.oauth import OAuthAccount
from app.db.models.user import User

# Rol por defecto en registro, coincide con el sembrado en la migración 0002.
ROLE_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111101")

_oauth = OAuth()
_configured = False


def configure_oauth() -> OAuth:
    """Registra el cliente Google en Authlib. Idempotente."""
    global _configured
    if _configured:
        return _oauth
    settings = get_settings()
    if settings.google_client_id and settings.google_client_secret:
        _oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )
    _configured = True
    return _oauth


def is_google_oauth_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def compute_redirect_uri(request: Request) -> str:
    """Deriva el callback URL del host actual (funciona en Codespaces y local).

    Si `ELI_GOOGLE_REDIRECT_URI` está definido, se usa. Si no, se construye a
    partir del request, que respeta el host público del Codespace.
    """
    settings = get_settings()
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/v1/auth/google/callback"


async def exchange_code_for_userinfo(request: Request, redirect_uri: str) -> dict[str, Any]:
    """Intercambia el code por un token y obtiene el userinfo de Google.

    Punto único de contacto con la red en el flujo OAuth. En tests se monkeypatchea.
    """
    oauth = configure_oauth()
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if userinfo is None:
        userinfo = await oauth.google.userinfo(token=token)
    return dict(userinfo)


async def link_or_create_google_user(
    session: AsyncSession,
    *,
    provider_user_id: str,
    email: str,
    name: str,
    picture: str | None,
) -> User:
    """Vincula o crea un User a partir del userinfo de Google.

    Reglas:
      1. Si ya existe OAuthAccount (google, sub) → devolver su user.
      2. Si existe un User con ese email → crear OAuthAccount y vincular.
      3. Si no existe → crear User (sin contraseña, rol USER) + OAuthAccount.
    """
    email = email.lower().strip()

    # 1) Ya vinculado
    stmt = select(OAuthAccount).where(
        OAuthAccount.provider == "google",
        OAuthAccount.provider_user_id == provider_user_id,
    )
    existing_link = await session.scalar(stmt)
    if existing_link is not None:
        user = await session.get(User, existing_link.user_id)
        if user is None:
            raise RuntimeError("OAuthAccount huérfano (integridad rota)")
        return user

    # 2) Mismo email
    stmt = select(User).where(User.email == email)
    user = await session.scalar(stmt)

    # 3) Crear si no existe
    if user is None:
        user = User(
            name=name or email.split("@")[0],
            email=email,
            password_hash=None,  # cuenta solo OAuth
            profile_image_url=picture,
            role_id=ROLE_USER_ID,
            status="ACTIVE",
        )
        session.add(user)
        await session.flush()

    # Crear el vínculo
    session.add(
        OAuthAccount(
            user_id=user.id,
            provider="google",
            provider_user_id=provider_user_id,
            email=email,
        )
    )
    await session.flush()
    return user