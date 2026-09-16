"""Endpoints de autenticación con email/contraseña.

Diseño de sesión:
  - Login exitoso → cookie httpOnly + Secure + SameSite.
  - La cookie lleva un token opaco; en BD vive solo su hash.
  - Logout revoca la sesión en servidor (no basta con borrar la cookie).

Rate limiting aplicado a login y register para mitigar fuerza bruta.

Incluye endpoints para la página de Ajustes:
  - PATCH /auth/me                  → editar nombre / email
  - POST  /auth/me/change-password  → cambiar contraseña
  - GET   /auth/me/preferences      → leer preferencias
  - PATCH /auth/me/preferences      → actualizar preferencias (merge)
  - POST  /auth/me/logout-all       → cerrar todas las sesiones
  - GET   /auth/me/export           → descargar todos mis datos (JSON)
  - DELETE /auth/me                 → eliminar mi cuenta
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
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
from app.db.models.conversation import Conversation
from app.db.models.document import Document
from app.db.models.memory import Memory
from app.db.models.message import Message
from app.db.models.role import Role
from app.db.models.user import User
from app.security.rate_limit import RateLimit

router = APIRouter(prefix="/auth", tags=["auth"])

ROLE_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111101")

# Nivel máximo de autonomía permitido por rol.
# El usuario no puede subir por encima de este valor con PATCH /me/preferences.
_MAX_AUTONOMY_BY_ROLE: dict[str, int] = {
    "USER": 2,
    "MODERATOR": 3,
    "ADMIN": 4,
    "SUPER_ADMIN": 4,
}


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
    profile_image_url: str | None = None
    last_login_at: datetime | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_model(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role.name if user.role else "USER",
            status=user.status,
            profile_image_url=user.profile_image_url,
            last_login_at=user.last_login_at,
            preferences=user.preferences or {},
        )


class UpdateProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class PreferencesIn(BaseModel):
    """Merge parcial sobre User.preferences. Solo se actualizan las claves enviadas.

    Claves conocidas:
      - autonomy_level: int 0-4
      - response_style: "concise" | "detailed" | "balanced"
      - language: "es" | "en" | ...
      - theme: "dark" | "light" | "system"
    """

    autonomy_level: int | None = Field(default=None, ge=0, le=4)
    response_style: str | None = Field(
        default=None, pattern="^(concise|detailed|balanced)$"
    )
    language: str | None = Field(default=None, min_length=2, max_length=10)
    theme: str | None = Field(default=None, pattern="^(dark|light|system)$")


class DeleteAccountIn(BaseModel):
    """Confirmación para eliminar la cuenta. Requiere teclear el email."""

    confirm_email: EmailStr


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
# Endpoints públicos
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


# --------------------------------------------------------------------------- #
# Me — lectura
# --------------------------------------------------------------------------- #
@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.from_model(user)


@router.get("/me/preferences")
async def get_preferences(
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Devuelve las preferencias actuales del usuario.

    Incluye `max_autonomy_level` y `role` calculados por el backend para que
    el frontend no duplique la regla de cap por rol.
    """
    role_name = user.role.name if user.role else "USER"
    max_level = _MAX_AUTONOMY_BY_ROLE.get(role_name, 2)

    prefs = dict(user.preferences or {})
    if "autonomy_level" not in prefs:
        prefs["autonomy_level"] = max_level
    prefs.setdefault("response_style", "balanced")
    prefs.setdefault("language", "es")
    prefs.setdefault("theme", "dark")

    # Metadatos derivados (no se persisten, se calculan en cada lectura)
    prefs["max_autonomy_level"] = max_level
    prefs["role"] = role_name
    return prefs


# --------------------------------------------------------------------------- #
# Me — edición
# --------------------------------------------------------------------------- #
@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateProfileIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> UserOut:
    """Actualiza nombre y/o email. Valida que el email siga siendo único."""
    if body.name is not None:
        user.name = body.name.strip()

    if body.email is not None:
        new_email = body.email.strip().lower()
        if new_email != user.email:
            exists = await session.scalar(
                select(User).where(
                    func.lower(User.email) == new_email,
                    User.id != user.id,
                )
            )
            if exists is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Ya existe otro usuario con ese email",
                )
            user.email = new_email

    await session.commit()
    await session.refresh(user, ["role"])
    return UserOut.from_model(user)


@router.patch("/me/preferences")
async def update_preferences(
    body: PreferencesIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    """Merge parcial. Solo se actualizan las claves enviadas.

    El autonomy_level está capado por rol: un USER no puede subir a 4.
    """
    payload = body.model_dump(exclude_none=True)

    # Cap de autonomía por rol
    if "autonomy_level" in payload:
        role_name = user.role.name if user.role else "USER"
        max_level = _MAX_AUTONOMY_BY_ROLE.get(role_name, 2)
        if payload["autonomy_level"] > max_level:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Tu rol ({role_name}) no puede superar el nivel "
                    f"de autonomía {max_level}."
                ),
            )

    prefs = dict(user.preferences or {})
    if payload:
        prefs.update(payload)
        user.preferences = prefs
        await session.commit()
    return prefs


@router.post("/me/change-password", status_code=204)
async def change_password(
    body: ChangePasswordIn,
    response: Response,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Cambia la contraseña y revoca todas las sesiones excepto la actual."""
    if not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="Esta cuenta no tiene contraseña (usa Google u otro OAuth)",
        )

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    try:
        user.password_hash = hash_password(body.new_password)
    except PasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Revocar todas las sesiones (incluida la actual)
    await SessionManager(session).revoke_all_for_user(user.id)

    # Crear sesión nueva para el dispositivo actual
    settings = get_settings()
    ip, ua = _client_meta(request)
    _, token = await SessionManager(session).create(user.id, ip=ip, user_agent=ua)

    await session.commit()
    _set_session_cookie(response, token, settings.session_ttl_days)
    response.status_code = 204
    return response


@router.post("/me/logout-all", status_code=204)
async def logout_all(
    response: Response,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Cierra TODAS las sesiones activas, incluida la actual."""
    await SessionManager(session).revoke_all_for_user(user.id)
    await session.commit()
    _clear_session_cookie(response)
    response.status_code = 204
    return response


# --------------------------------------------------------------------------- #
# Me — exportar y eliminar
# --------------------------------------------------------------------------- #
@router.get("/me/export")
async def export_my_data(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    """Devuelve todos los datos del usuario como JSON."""
    convs = list(
        (
            await session.scalars(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.created_at.asc())
            )
        ).all()
    )

    conv_ids = [c.id for c in convs]
    messages: list[Message] = []
    if conv_ids:
        messages = list(
            (
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id.in_(conv_ids))
                    .order_by(Message.created_at.asc())
                )
            ).all()
        )

    memories = list(
        (
            await session.scalars(
                select(Memory)
                .where(Memory.user_id == user.id)
                .order_by(Memory.created_at.asc())
            )
        ).all()
    )

    documents = list(
        (
            await session.scalars(
                select(Document)
                .where(Document.owner_user_id == user.id)
                .order_by(Document.created_at.asc())
            )
        ).all()
    )

    msgs_by_conv: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for m in messages:
        msgs_by_conv.setdefault(m.conversation_id, []).append(
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "tokens_in": m.tokens_in,
                "tokens_out": m.tokens_out,
                "model": m.model,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role.name if user.role else None,
            "status": user.status,
            "preferences": user.preferences or {},
            "profile_image_url": user.profile_image_url,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        },
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "model": c.model,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "messages": msgs_by_conv.get(c.id, []),
            }
            for c in convs
        ],
        "memories": [
            {
                "id": str(m.id),
                "type": m.type,
                "content": m.content,
                "importance": m.importance,
                "confidence": m.confidence,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ],
        "documents": [
            {
                "id": str(d.id),
                "title": d.title,
                "mime_type": d.mime_type,
                "size_bytes": d.size_bytes,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "summary": d.summary,
                "topics": d.topics,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in documents
        ],
    }


@router.delete("/me", status_code=204)
async def delete_my_account(
    body: DeleteAccountIn,
    response: Response,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Elimina la cuenta del usuario.

    Estrategia:
      - Hard delete: conversaciones, memorias, documentos (y chunks por cascade).
      - Anonimizar: email, nombre, contraseña, avatar.
      - Soft delete: status=DELETED (mantiene la fila para auditoría).
      - Revocar todas las sesiones.
    """
    if body.confirm_email.strip().lower() != user.email.lower():
        raise HTTPException(
            status_code=400,
            detail="El email de confirmación no coincide",
        )

    await session.execute(
        delete(Conversation).where(Conversation.user_id == user.id)
    )
    await session.execute(delete(Memory).where(Memory.user_id == user.id))
    await session.execute(
        delete(Document).where(Document.owner_user_id == user.id)
    )

    await SessionManager(session).revoke_all_for_user(user.id)

    user.email = f"deleted-{user.id}@deleted.eli.local"
    user.name = "Cuenta eliminada"
    user.password_hash = None
    user.profile_image_url = None
    user.status = "DELETED"

    await session.commit()
    _clear_session_cookie(response)
    response.status_code = 204
    return response


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