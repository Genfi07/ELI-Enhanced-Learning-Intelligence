"""Rate limiting por ventana deslizante.

Diseño:
  - Cada clave (user_id, ip, etc.) tiene una cola de timestamps de hits.
  - Al comprobar un hit, se descartan los timestamps más antiguos que la
    ventana y se cuenta cuántos quedan. Si la cuenta alcanza el límite,
    el hit se rechaza.
  - Los hits admitidos se registran.
  - Es "en memoria": no persiste entre procesos. Para producción multi-worker
    se cambia por Redis con la misma interfaz.

Uso desde un endpoint:

    from fastapi import Depends
    from app.security.rate_limit import RateLimit

    @router.post("/auth/login", dependencies=[Depends(RateLimit("login", 5, 60))])
    async def login(...): ...

El límite `login=5, window=60` significa: máximo 5 intentos por minuto
por clave. La clave por defecto es la IP del request. Se puede personalizar
con `key_func`.

Errores:
  - Cuando se excede, se lanza HTTPException 429 con `Retry-After` (segundos).
  - El mensaje incluye el tiempo restante.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.observability.logging import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Limiter
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(self) -> None:
        # key -> deque de timestamps monotónicos
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        # Último GC
        self._last_gc: float = 0.0

    async def check_and_record(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: float,
    ) -> tuple[bool, float]:
        """Intenta consumir un hit.

        Devuelve (allowed, retry_after_seconds).
        Si allowed=False, retry_after_seconds indica cuánto falta para que
        el hit más antiguo salga de la ventana.
        """
        if limit <= 0:
            return True, 0.0  # límite desactivado
        now = time.monotonic()
        cutoff = now - window_seconds

        async with self._lock:
            dq = self._hits[key]
            # Descartar hits fuera de la ventana
            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= limit:
                # Rechazado. retry_after = cuándo saldrá el más antiguo.
                oldest = dq[0]
                retry_after = max(0.1, oldest + window_seconds - now)
                return False, retry_after

            dq.append(now)
            self._gc_if_needed(now)
            return True, 0.0

    def reset(self, key: str) -> None:
        """Resetea el contador de una clave (usado tras login exitoso, etc.)."""
        self._hits.pop(key, None)

    def reset_all(self) -> None:
        self._hits.clear()

    # ------------------------------------------------------------------ #
    # Garbage collection
    # ------------------------------------------------------------------ #
    def _gc_if_needed(self, now: float) -> None:
        """Purga claves antiguas para no crecer indefinidamente.

        Corre como máximo cada 60 s. Purga claves sin hits en los últimos
        5 minutos.
        """
        if now - self._last_gc < 60.0:
            return
        self._last_gc = now
        stale_cutoff = now - 300.0
        stale_keys = [
            k for k, dq in self._hits.items()
            if not dq or dq[-1] < stale_cutoff
        ]
        for k in stale_keys:
            del self._hits[k]
        if stale_keys:
            log.debug("rate_limiter_gc", freed=len(stale_keys))


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #
_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    return _limiter


# --------------------------------------------------------------------------- #
# Dependencia FastAPI
# --------------------------------------------------------------------------- #
def _default_key_func(request: Request) -> str:
    """Por defecto: IP del cliente. En endpoints autenticados conviene
    pasar una key_func que use el user_id."""
    if request.client and request.client.host:
        return f"ip:{request.client.host}"
    return "ip:unknown"


class RateLimit:
    """Dependencia parametrizable.

    Uso:
        Depends(RateLimit("login", limit=5, window_seconds=60))
        Depends(RateLimit("chat", limit=30, window_seconds=60, key_func=user_key))
    """

    def __init__(
        self,
        scope: str,
        limit: int,
        window_seconds: float,
        *,
        key_func: Callable[[Request], str] | None = None,
    ) -> None:
        self.scope = scope
        self.limit = limit
        self.window_seconds = window_seconds
        self.key_func = key_func or _default_key_func

    async def __call__(self, request: Request) -> None:
        raw_key = self.key_func(request)
        key = f"{self.scope}:{raw_key}"
        allowed, retry_after = await _limiter.check_and_record(
            key, limit=self.limit, window_seconds=self.window_seconds
        )
        if not allowed:
            wait_s = int(retry_after) + 1
            log.info(
                "rate_limit_exceeded",
                scope=self.scope,
                key=raw_key,
                retry_after=wait_s,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiadas peticiones. Reintenta en {wait_s} s.",
                headers={"Retry-After": str(wait_s)},
            )