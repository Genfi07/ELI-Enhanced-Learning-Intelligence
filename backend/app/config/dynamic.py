"""Sistema de configuración dinámica.

Diseño:
  - `Settings` (app.config.settings) sigue siendo la fuente de DEFAULTS.
  - `system_settings` (BD) contiene SOLO overrides guardados por admins.
  - `DynamicSettings` fusiona ambos y cachea el resultado con TTL.

Uso típico:
    from app.config.dynamic import get_dynamic

    # Leer un setting (usa caché):
    value = await get_dynamic("memory_top_k")

    # Leer varios:
    values = await get_many_dynamic(["memory_top_k", "rag_top_k"])

    # Tras un cambio admin (en el endpoint que guarda):
    invalidate_dynamic_cache()

Reglas:
  - Si la clave no está en BD → se devuelve el default de Settings.
  - Si la clave está en BD → se devuelve ese valor (prioridad sobre default).
  - Las claves desconocidas devuelven None.
  - La caché es por proceso y global (singleton). No hay invalidación
    distribuida: si en el futuro hay varios workers, se cambia por Redis pub/sub.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import select

from app.config.settings import Settings, get_settings
from app.db.models.system import SystemSetting
from app.db.session import session_scope
from app.observability.logging import get_logger

log = get_logger(__name__)


CACHE_TTL_SECONDS = 30.0


class _Cache:
    """Caché simple en memoria con TTL. Thread-safe con un lock."""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    def is_fresh(self) -> bool:
        return (time.monotonic() - self._loaded_at) < CACHE_TTL_SECONDS

    def get(self, key: str) -> tuple[bool, Any]:
        """(encontrado_en_cache, valor)."""
        if key in self._values:
            return True, self._values[key]
        return False, None

    def set_all(self, values: dict[str, Any]) -> None:
        self._values = values
        self._loaded_at = time.monotonic()

    def invalidate(self) -> None:
        self._values = {}
        self._loaded_at = 0.0


_cache = _Cache()


async def _load_overrides() -> dict[str, Any]:
    """Carga TODOS los overrides desde BD de una vez."""
    async with session_scope() as session:
        rows = list(
            (await session.scalars(select(SystemSetting))).all()
        )
        return {r.key: r.value for r in rows}


async def _ensure_cache() -> None:
    """Garantiza que la caché está cargada y fresca."""
    if _cache.is_fresh():
        return
    async with _cache._lock:
        # Double-check tras adquirir el lock
        if _cache.is_fresh():
            return
        try:
            overrides = await _load_overrides()
            _cache.set_all(overrides)
            log.debug("dynamic_settings_cache_loaded", count=len(overrides))
        except Exception as exc:
            # Si la BD falla, no bloqueamos: usamos defaults y reintentamos luego.
            log.warning("dynamic_settings_load_failed", error=str(exc))
            _cache.set_all({})


def _default_for(key: str) -> Any:
    """Lee el default del Settings codebase."""
    settings: Settings = get_settings()
    if hasattr(settings, key):
        return getattr(settings, key)
    return None


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
async def get_dynamic(key: str, default: Any = None) -> Any:
    """Devuelve el valor efectivo de una clave.

    Orden de prioridad:
      1. Override en `system_settings`.
      2. Default en Settings.
      3. `default` pasado por el caller.
    """
    await _ensure_cache()
    found, value = _cache.get(key)
    if found:
        return value
    code_default = _default_for(key)
    if code_default is not None:
        return code_default
    return default


async def get_many_dynamic(keys: list[str]) -> dict[str, Any]:
    """Igual que get_dynamic pero en batch."""
    await _ensure_cache()
    out: dict[str, Any] = {}
    for k in keys:
        found, value = _cache.get(k)
        if found:
            out[k] = value
        else:
            code_default = _default_for(k)
            if code_default is not None:
                out[k] = code_default
    return out


def invalidate_dynamic_cache() -> None:
    """Fuerza recarga en la próxima lectura. Llamar tras cambios admin."""
    _cache.invalidate()

# --------------------------------------------------------------------------- #
# Enmascarado de secretos
# --------------------------------------------------------------------------- #
# Cualquier clave que termine así se considera secreta y se enmascara
# cuando el usuario no es SUPER_ADMIN.
_SECRET_SUFFIXES = (
    "_api_key",
    "_secret",
    "_token",
    "_password",
)
_SECRET_EXACT = {
    "secret_key",
    "database_url",
}


def is_secret_key(key: str) -> bool:
    """True si la clave debe tratarse como secreto."""
    if key in _SECRET_EXACT:
        return True
    return any(key.endswith(s) for s in _SECRET_SUFFIXES)


def _mask_secret(value: Any) -> Any:
    """Enmascara un valor secreto mostrando solo el principio y el final.

    - Strings: 'sk-abc...xyz'
    - None o vacíos: se devuelven tal cual
    - Otros tipos: '••••'
    """
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        return "••••••"
    if len(value) <= 12:
        return "••••••"
    return f"{value[:6]}…{value[-4:]}"

async def list_all_settings_with_metadata(
    *, include_secrets: bool = False
) -> list[dict[str, Any]]:
    """Devuelve todas las claves conocidas (defaults + overrides) con metadata.

    Útil para el panel de admin: permite mostrar el default, el valor actual,
    y si el valor actual es un override o el default del código.

    Si `include_secrets=False` (default), las claves secretas se devuelven
    enmascaradas (tipo `sk-abc…xyz`). Solo SUPER_ADMIN debe llamar con
    `include_secrets=True`.
    """
    settings: Settings = get_settings()
    defaults = settings.model_dump()

    async with session_scope() as session:
        rows = list((await session.scalars(select(SystemSetting))).all())
        overrides = {r.key: r for r in rows}

    all_keys = set(defaults.keys()) | set(overrides.keys())

    out: list[dict[str, Any]] = []
    for key in sorted(all_keys):
        default_value = defaults.get(key)
        override = overrides.get(key)
        raw_value = override.value if override else default_value

        secret = is_secret_key(key)
        if secret and not include_secrets:
            shown_value = _mask_secret(raw_value)
            shown_default = _mask_secret(default_value)
        else:
            shown_value = raw_value
            shown_default = default_value

        out.append(
            {
                "key": key,
                "default": shown_default,
                "value": shown_value,
                "is_override": override is not None,
                "is_secret": secret,
                "category": override.category if override else _infer_category(key),
                "description": override.description if override else None,
                "updated_at": override.updated_at if override else None,
                "updated_by": override.updated_by if override else None,
            }
        )
    return out

async def set_dynamic_setting(
    key: str,
    value: Any,
    *,
    category: str = "general",
    description: str | None = None,
    updated_by: Any = None,
) -> SystemSetting:
    """Crea o actualiza un override. Devuelve la fila persistida."""
    async with session_scope() as session:
        existing = await session.scalar(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        if existing is None:
            existing = SystemSetting(
                key=key,
                value=value,
                category=category,
                description=description,
                updated_by=updated_by,
            )
            session.add(existing)
        else:
            existing.value = value
            existing.category = category
            if description is not None:
                existing.description = description
            existing.updated_by = updated_by
        await session.flush()
        # Guardar copia de atributos antes de salir de la sesión
        result = {
            "id": existing.id,
            "key": existing.key,
            "value": existing.value,
            "category": existing.category,
            "description": existing.description,
            "updated_by": existing.updated_by,
        }
    invalidate_dynamic_cache()
    # Devolvemos un objeto desligado de la sesión (dict convertible)
    return result  # type: ignore[return-value]


async def delete_dynamic_setting(key: str) -> bool:
    """Elimina un override. Tras esto, la clave vuelve al default del código."""
    async with session_scope() as session:
        existing = await session.scalar(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        if existing is None:
            return False
        await session.delete(existing)
    invalidate_dynamic_cache()
    return True


# --------------------------------------------------------------------------- #
# Categorización heurística (para el panel admin)
# --------------------------------------------------------------------------- #
def _infer_category(key: str) -> str:
    if key.startswith("llm_"):
        return "llm"
    if key.startswith("memory_"):
        return "memory"
    if key.startswith("planning_"):
        return "reasoning"
    if key.startswith("rag_"):
        return "rag"
    if key.startswith("summarization_"):
        return "reasoning"
    if key.startswith("cookie_") or key.startswith("session_"):
        return "security"
    if key.startswith("google_") or key.startswith("oauth_"):
        return "auth"
    if key.startswith("web_"):
        return "tools"
    return "general"