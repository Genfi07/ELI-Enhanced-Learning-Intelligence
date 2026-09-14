import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from app.core.schemas.turn import TurnTrace


class TraceBuilder:
    """Acumula los pasos de un turno y produce un TurnTrace al final."""

    def __init__(self, *, user_id, conversation_id, route: str, plan: dict) -> None:
        self.request_id = uuid.uuid4().hex
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.route = route
        self.plan = plan
        self.steps: list[dict[str, Any]] = []
        self._started = time.perf_counter()
        self.status = "ok"
        self.error: str | None = None

    @asynccontextmanager
    async def step(self, name: str, **meta: Any):
        """Context manager de un paso.

        Uso:
            async with trace.step("build_context", plan=plan.route) as s:
                ...
                s["meta"]["memory"] = "skipped"   # anotaciones libres

        El diccionario 's' es mutable y se persiste con la traza.
        """
        t0 = time.perf_counter()
        entry: dict[str, Any] = {
            "name": name,
            "meta": dict(meta),
            "status": "ok",
            "latency_ms": 0,
            "error": None,
        }
        try:
            yield entry
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)
            self.status = "error"
            self.error = str(exc)
            raise
        finally:
            entry["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            self.steps.append(entry)

    def to_trace(self) -> TurnTrace:
        return TurnTrace(
            request_id=self.request_id,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            route=self.route,
            plan=self.plan,
            steps=self.steps,
            total_latency_ms=int((time.perf_counter() - self._started) * 1000),
            status=self.status,
            error=self.error,
        )