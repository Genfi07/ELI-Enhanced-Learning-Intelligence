"""Endpoints de autenticación con email/contraseña.

Diseño de sesión:
  - Login exitoso → cookie httpOnly + Secure + SameSite.
  - La cookie lleva un token opaco; en BD vive solo su hash.
  - Logout revoca la sesión en servidor (no basta con borrar la cookie).

Rate limiting aplicado a login y register para mitigar fuerza bruta.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import COOKIE_NAME, current_user, db_session
from app.auth.oauth_google import (
    compute_redirect_uri,
    configure_oauth,
    exchange_code_for_userinfo,
    is_google_oauth_configured,
    link_or_create_google_user,
)
from app.auth.passwords import PasswordError, hash_password, verify_password
from app.auth.session import SessionManager
from app.config.settings import get_settings
from app.db.models.role import Role
from app.db.models.user import User
from app.security.rate_limit import RateLimit

router = APIRouter(prefix="/auth", tags=["auth"])

ROLE_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111101")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    status: str

    @classmethod
    def from_model(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role.name if user.role else "USER",
            status=user.status,
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _set_session_cookie(response: Response, token: str, ttl_days: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        domain=settings.cookie_domain,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=COOKIE_NAME,
        domain=settings.cookie_domain,
        path="/",
    )


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(RateLimit("register", limit=10, window_seconds=60))],
)
async def register(
    body: RegisterIn,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> UserOut:
    existing = await session.scalar(select(User).where(User.email == body.email.lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email ya registrado")

    role = await session.get(Role, ROLE_USER_ID)
    if role is None:
        raise HTTPException(status_code=500, detail="Rol USER no encontrado")

    try:
        pwd_hash = hash_password(body.password)
    except PasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = User(
        name=body.name,
        email=body.email.lower(),
        password_hash=pwd_hash,
        role_id=role.id,
        status="ACTIVE",
    )
    session.add(user)
    await session.flush()

    settings = get_settings()
    ip, ua = _client_meta(request)
    _, token = await SessionManager(session).create(user.id, ip=ip, user_agent=ua)
    await session.commit()

    _set_session_cookie(response, token, settings.session_ttl_days)
    await session.refresh(user, ["role"])
    return UserOut.from_model(user)


@router.post(
    "/login",
    response_model=UserOut,
    dependencies=[Depends(RateLimit("login", limit=5, window_seconds=60))],
)
async def login(
    body: LoginIn,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> UserOut:
    user = await session.scalar(select(User).where(User.email == body.email.lower()))

    if user is None or not user.password_hash:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    if user.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Cuenta bloqueada o inactiva")

    settings = get_settings()
    ip, ua = _client_meta(request)
    _, token = await SessionManager(session).create(user.id, ip=ip, user_agent=ua)

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    _set_session_cookie(response, token, settings.session_ttl_days)
    await session.refresh(user, ["role"])
    return UserOut.from_model(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await SessionManager(session).revoke(token)
        await session.commit()
    _clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.from_model(user)


# --------------------------------------------------------------------------- #
# Google OAuth
# --------------------------------------------------------------------------- #
@router.get("/google/start")
async def google_start(request: Request):
    if not is_google_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth no configurado en este entorno",
        )
    oauth = configure_oauth()
    redirect_uri = compute_redirect_uri(request)
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    session: AsyncSession = Depends(db_session),
):
    if not is_google_oauth_configured():
        raise HTTPException(status_code=503, detail="Google OAuth no configurado")

    redirect_uri = compute_redirect_uri(request)
    try:
        userinfo = await exchange_code_for_userinfo(request, redirect_uri)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Falló autenticación con Google") from exc

    sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name") or userinfo.get("given_name") or ""
    picture = userinfo.get("picture")

    if not sub or not email:
        raise HTTPException(status_code=400, detail="Google no devolvió sub/email")

    user = await link_or_create_google_user(
        session,
        provider_user_id=str(sub),
        email=email,
        name=name,
        picture=picture,
    )

    if user.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Cuenta bloqueada")

    settings = get_settings()
    ip, ua = _client_meta(request)
    _, token = await SessionManager(session).create(user.id, ip=ip, user_agent=ua)

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    response = RedirectResponse(url=settings.oauth_redirect_after_login, status_code=302)
    _set_session_cookie(response, token, settings.session_ttl_days)
    return response