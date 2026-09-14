"""Gestión de sesiones.

Modelo de seguridad:
  - Al hacer login, se genera un token aleatorio (32 bytes → 256 bits de entropía).
  - El token se envía en una cookie httpOnly+Secure+SameSite=Lax.
  - En BD guardamos SOLO el hash SHA-256 del token, no el token.
    Así, si la BD se filtra, las cookies robadas no son utilizables.
  - En cada request, se hashea el token entrante y se busca por ese hash.

Por qué SHA-256 y no Argon2 aquí:
  El token ya tiene 256 bits de entropía — no es adivinable por fuerza bruta.
  Argon2 está diseñado para proteger secretos débiles (contraseñas humanas).
  Para tokens aleatorios, un hash rápido es lo correcto.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.session import Session as SessionModel


TOKEN_BYTES = 32                  # 256 bits
SESSION_TTL = timedelta(days=30)  # duración por defecto


def _generate_token() -> str:
    """Token opaco, URL-safe, 43 caracteres."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionManager:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
        ttl: timedelta | None = None,
    ) -> tuple[SessionModel, str]:
        """Crea una sesión y devuelve (modelo, token_en_claro).

        El token en claro SOLO se devuelve aquí. Después no se puede recuperar.
        """
        token = _generate_token()
        now = datetime.now(timezone.utc)
        model = SessionModel(
            user_id=user_id,
            session_token_hash=_hash_token(token),
            expires_at=now + (ttl or SESSION_TTL),
            ip=ip,
            user_agent=(user_agent or "")[:500] or None,
            last_used_at=now,
        )
        self.session.add(model)
        await self.session.flush()
        return model, token

    async def validate(self, token: str) -> SessionModel | None:
        """Valida el token y devuelve la sesión si es válida.

        Devuelve None si:
          - El token no existe.
          - La sesión está revocada.
          - La sesión está expirada.
        Actualiza last_used_at si todo está bien.
        """
        if not token:
            return None
        token_hash = _hash_token(token)
        stmt = select(SessionModel).where(SessionModel.session_token_hash == token_hash)
        sess = await self.session.scalar(stmt)
        if sess is None:
            return None
        now = datetime.now(timezone.utc)
        if sess.revoked_at is not None:
            return None
        if sess.expires_at <= now:
            return None
        sess.last_used_at = now
        return sess

    async def revoke(self, token: str) -> bool:
        """Marca la sesión como revocada. Idempotente."""
        if not token:
            return False
        sess = await self.validate(token)
        if sess is None:
            # Puede que esté expirada o revocada. Buscamos igual para marcarla.
            token_hash = _hash_token(token)
            stmt = select(SessionModel).where(SessionModel.session_token_hash == token_hash)
            sess = await self.session.scalar(stmt)
            if sess is None:
                return False
        if sess.revoked_at is None:
            sess.revoked_at = datetime.now(timezone.utc)
        return True

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoca todas las sesiones activas de un usuario. Devuelve el número afectado."""
        now = datetime.now(timezone.utc)
        stmt = select(SessionModel).where(
            SessionModel.user_id == user_id,
            SessionModel.revoked_at.is_(None),
            SessionModel.expires_at > now,
        )
        sessions = list((await self.session.scalars(stmt)).all())
        for s in sessions:
            s.revoked_at = now
        return len(sessions)