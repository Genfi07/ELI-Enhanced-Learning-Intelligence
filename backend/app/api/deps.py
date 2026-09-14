"""Dependencias compartidas de FastAPI.

Aquí vive la autenticación real:
  - `current_user` lee la cookie de sesión, la valida y devuelve el User.
  - En entornos dev/test, acepta además el header X-Dev-User-Id como atajo
    (para no obligar a hacer login en cada iteración de desarrollo).

En producción (ELI_ENV=prod), el header X-Dev-User-Id se ignora por completo.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models.user import User
from app.db.session import get_sessionmaker

COOKIE_NAME = "eli_session"


async def db_session() -> AsyncIterator[AsyncSession]:
    """Sesión de BD por request. `async with` ya cierra la sesión al salir;
    no hace falta un close() extra (podía disparar IO fuera del contexto greenlet)."""
    async with get_sessionmaker()() as s:
        yield s


async def current_user(
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> User:
    """Devuelve el usuario autenticado o lanza 401.

    Orden de resolución:
      1. Cookie `eli_session` con token de sesión válido.
      2. Si el entorno es dev/test, header X-Dev-User-Id (atajo de desarrollo).
    """
    # Import diferido para evitar ciclo (rbac → deps → rbac)
    from app.auth.session import SessionManager

    # 1) Cookie de sesión
    token = request.cookies.get(COOKIE_NAME)
    if token:
        sess = await SessionManager(session).validate(token)
        if sess is not None:
            user = await session.get(User, sess.user_id)
            if user is not None and user.status == "ACTIVE":
                return user

    # 2) Atajo dev/test
    settings = get_settings()
    if settings.env in ("dev", "test"):
        dev_header = request.headers.get("X-Dev-User-Id")
        if dev_header:
            try:
                uid = uuid.UUID(dev_header)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="X-Dev-User-Id inválido",
                ) from exc
            user = await session.get(User, uid)
            if user is not None and user.status == "ACTIVE":
                return user
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado o inactivo",
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado",
    )


async def current_user_id(user: User = Depends(current_user)) -> uuid.UUID:
    """Atajo para handlers que solo necesitan el id."""
    return user.id