"""Sistema de autonomía y autorización de herramientas.

Niveles (spec §18):
  0 — Solo conversación. Ninguna tool ejecutable.
  1 — Lectura de información (consultas, sin efectos).
  2 — Uso de herramientas internas (calculator, datetime).
  3 — Acciones externas reversibles (web_search, web_fetch).
  4 — Acciones sensibles con confirmación explícita del usuario.

Nivel del usuario: vive en `user.preferences["autonomy_level"]`. Default 2.
Un admin puede subirlo/bajarlo con el panel de admin (Fase 7).

Autorización de una tool: se combinan tres señales:
  1. La tool está enabled en BD (un admin no la ha desactivado).
  2. El usuario tiene el nivel de autonomía suficiente.
  3. El usuario tiene los permisos RBAC requeridos.

Si las tres pasan y la tool requiere confirmación → REQUIRE_CONFIRMATION.
Si las tres pasan y no requiere confirmación → ALLOW.
Cualquier otra combinación → DENY con razón explícita.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.schemas.tool import ToolManifest
from app.db.models.user import User


Decision = Literal["ALLOW", "DENY", "REQUIRE_CONFIRMATION"]
DEFAULT_AUTONOMY_LEVEL = 2
MAX_AUTONOMY_LEVEL = 4


@dataclass
class AuthorizationResult:
    decision: Decision
    reason: str
    user_autonomy_level: int


# --------------------------------------------------------------------------- #
# Lectura / escritura del nivel
# --------------------------------------------------------------------------- #
def get_user_autonomy_level(user: User) -> int:
    """Devuelve el nivel de autonomía efectivo del usuario.

    Si el usuario es ADMIN o SUPER_ADMIN, el default es 4 (control total),
    salvo que tenga un valor explícito en preferences.
    """
    prefs = user.preferences or {}
    raw = prefs.get("autonomy_level")
    if isinstance(raw, int) and 0 <= raw <= MAX_AUTONOMY_LEVEL:
        return raw

    role = getattr(user, "role", None)
    role_name = role.name if role is not None else "USER"
    if role_name in ("ADMIN", "SUPER_ADMIN"):
        return 4
    return DEFAULT_AUTONOMY_LEVEL


def set_user_autonomy_level(user: User, level: int) -> None:
    """Modifica el nivel en `preferences`. No persiste — el caller hace commit."""
    if not 0 <= level <= MAX_AUTONOMY_LEVEL:
        raise ValueError(f"nivel fuera de rango: {level}")
    prefs = dict(user.preferences or {})
    prefs["autonomy_level"] = level
    user.preferences = prefs


# --------------------------------------------------------------------------- #
# Autorización
# --------------------------------------------------------------------------- #
def authorize_tool(
    user: User,
    manifest: ToolManifest,
    *,
    tool_enabled_in_db: bool = True,
) -> AuthorizationResult:
    """Decide si el usuario puede invocar la tool.

    Nunca lanza. Devuelve una razón legible para auditoría.
    """
    user_level = get_user_autonomy_level(user)

    # 1. Tool desactivada por admin
    if not tool_enabled_in_db:
        return AuthorizationResult(
            decision="DENY",
            reason=f"tool '{manifest.name}' está desactivada por el administrador",
            user_autonomy_level=user_level,
        )
    if not manifest.enabled:
        return AuthorizationResult(
            decision="DENY",
            reason=f"tool '{manifest.name}' está deshabilitada globalmente",
            user_autonomy_level=user_level,
        )

    # 2. Nivel de autonomía
    if user_level < manifest.min_autonomy_level:
        return AuthorizationResult(
            decision="DENY",
            reason=(
                f"se requiere autonomía >= {manifest.min_autonomy_level}; "
                f"el usuario tiene {user_level}"
            ),
            user_autonomy_level=user_level,
        )

    # 3. Permisos RBAC
    if manifest.required_permissions:
        role = getattr(user, "role", None)
        role_perms = {p.code for p in (role.permissions if role else [])}
        missing = [p for p in manifest.required_permissions if p not in role_perms]
        if missing:
            return AuthorizationResult(
                decision="DENY",
                reason=f"faltan permisos: {', '.join(missing)}",
                user_autonomy_level=user_level,
            )

    # 4. Confirmación explícita
    if manifest.requires_confirmation:
        return AuthorizationResult(
            decision="REQUIRE_CONFIRMATION",
            reason=(
                f"'{manifest.name}' es una acción sensible; "
                "requiere confirmación del usuario"
            ),
            user_autonomy_level=user_level,
        )

    return AuthorizationResult(
        decision="ALLOW",
        reason="autorizado",
        user_autonomy_level=user_level,
    )