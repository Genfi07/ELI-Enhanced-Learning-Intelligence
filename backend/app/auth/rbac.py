"""Control de acceso basado en roles (RBAC).

Diseño:
  - Los permisos son strings con formato "recurso.accion" (ej: "users.write").
  - Cada rol tiene un conjunto de permisos.
  - Las rutas declaran `dependencies=[Depends(require_permission("users.write"))]`
    y FastAPI verifica ANTES de ejecutar el handler.
  - Nunca se confía en el frontend para ocultar acciones: el backend deniega.
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status

from app.api.deps import current_user
from app.db.models.user import User


def has_permission(user: User, code: str) -> bool:
    """True si el usuario tiene el permiso indicado a través de su rol."""
    role = getattr(user, "role", None)
    if role is None:
        return False
    return any(p.code == code for p in role.permissions)


def require_permission(
    code: str,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Devuelve una dependencia de FastAPI que exige el permiso indicado.

    Uso:
        @router.get("/users", dependencies=[Depends(require_permission("users.read"))])
        async def list_users(): ...

    O si necesitas el usuario dentro del handler:
        async def list_users(user: User = Depends(require_permission("users.read"))): ...
    """

    async def _checker(user: User = Depends(current_user)) -> User:
        if not has_permission(user, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {code}",
            )
        return user

    return _checker