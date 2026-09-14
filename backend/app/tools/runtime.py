"""ToolRuntime: ejecuta herramientas con autorización y auditoría.

Flujo de una invocación:
  1. Validar que la tool existe en el registry.
  2. Consultar si un admin la desactivó (`is_enabled_in_db`).
  3. Autorizar con `authorize_tool`:
       - DENY → registrar ToolCall con status DENIED, devolver DENIED.
       - REQUIRE_CONFIRMATION → crear PendingAction, devolver PENDING_CONFIRMATION.
       - ALLOW → continuar.
  4. Validar argumentos contra `manifest.parameters` (JSON Schema) si existe.
  5. Ejecutar con timeout (`asyncio.wait_for`).
  6. Registrar ToolCall con status OK / ERROR / TIMEOUT.
  7. Devolver resultado.

Reglas de auditoría:
  - TODA invocación (incluso DENIED) deja un ToolCall en BD.
  - Los resultados se truncan a `max_result_chars` antes de guardar.
  - El runtime nunca lanza: cualquier fallo se refleja en el ToolCall.

Confirmación nivel 4:
  - El runtime NO ejecuta. Crea un PendingAction con expiración (default 1h).
  - El usuario confirma con `POST /tools/pending-actions/{id}/confirm`.
  - Ese endpoint llama a `runtime.execute_pending(...)` que ejecuta y
    actualiza el PendingAction + crea ToolCall.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.core.schemas.tool import ToolInvokeOut
from app.db.models.tool import PendingAction, ToolCall
from app.db.models.user import User
from app.observability.logging import get_logger
from app.tools.autonomy import authorize_tool
from app.tools.registry import ToolRegistry

log = get_logger(__name__)


DEFAULT_PENDING_TTL_MINUTES = 60
MAX_RESULT_CHARS = 8_000


# --------------------------------------------------------------------------- #
# Validación de argumentos
# --------------------------------------------------------------------------- #
def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Valida `arguments` contra `schema` (JSON Schema básico).

    Devuelve un mensaje de error legible, o None si todo OK.
    Solo soportamos:
      - type: "object" con properties/required
      - tipos simples: string, integer, number, boolean, array, object
    Si el schema no declara `type`, no validamos (permisivo).

    No usamos `jsonschema` para no añadir dependencia. Si en el futuro
    alguien necesita schemas complejos, se cambia a jsonschema sin tocar
    el resto del runtime.
    """
    if not schema or schema.get("type") != "object":
        return None
    props = schema.get("properties") or {}
    required = schema.get("required") or []

    for key in required:
        if key not in arguments:
            return f"falta argumento requerido: {key}"

    for key, value in arguments.items():
        if key not in props:
            continue  # argumento extra: toleramos
        expected = props[key].get("type")
        if expected is None:
            continue
        if expected == "string" and not isinstance(value, str):
            return f"'{key}' debe ser string"
        if expected == "integer" and not isinstance(value, int):
            return f"'{key}' debe ser integer"
        if expected == "number" and not isinstance(value, (int, float)):
            return f"'{key}' debe ser number"
        if expected == "boolean" and not isinstance(value, bool):
            return f"'{key}' debe ser boolean"
        if expected == "array" and not isinstance(value, list):
            return f"'{key}' debe ser array"
        if expected == "object" and not isinstance(value, dict):
            return f"'{key}' debe ser object"
    return None


def _truncate(value: Any, max_chars: int = MAX_RESULT_CHARS) -> Any:
    """Trunca strings y JSON grandes antes de guardar en BD."""
    if value is None:
        return None
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "... [truncado]"
    try:
        import json
        raw = json.dumps(value, ensure_ascii=False)
        if len(raw) > max_chars:
            return {"_truncated": True, "preview": raw[:max_chars]}
    except (TypeError, ValueError):
        pass
    return value


# --------------------------------------------------------------------------- #
# Runtime
# --------------------------------------------------------------------------- #
@dataclass
class ToolInvocationContext:
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None
    message_id: uuid.UUID | None


class ToolRuntime:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    async def invoke(
        self,
        session: AsyncSession,
        *,
        user: User,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
    ) -> ToolInvokeOut:
        """Invoca una tool. Nunca lanza: devuelve siempre un ToolInvokeOut."""
        started = time.perf_counter()

        # 1. ¿Existe la tool?
        tool = self.registry.get(tool_name)
        if tool is None:
            await self._record_call(
                session,
                user_id=user.id,
                conversation_id=context.conversation_id,
                message_id=context.message_id,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                status="DENIED",
                error=f"tool desconocida: {tool_name}",
                autonomy_level=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            return ToolInvokeOut(
                status="DENIED",
                tool_name=tool_name,
                error=f"tool desconocida: {tool_name}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        # 2. ¿Está habilitada en BD?
        enabled_in_db = await self.registry.is_enabled_in_db(tool_name)

        # 3. Autorizar
        decision = authorize_tool(user, tool.manifest, tool_enabled_in_db=enabled_in_db)

        if decision.decision == "DENY":
            await self._record_call(
                session,
                user_id=user.id,
                conversation_id=context.conversation_id,
                message_id=context.message_id,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                status="DENIED",
                error=decision.reason,
                autonomy_level=decision.user_autonomy_level,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            return ToolInvokeOut(
                status="DENIED",
                tool_name=tool_name,
                error=decision.reason,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        if decision.decision == "REQUIRE_CONFIRMATION":
            pending = await self._create_pending(
                session,
                user_id=user.id,
                conversation_id=context.conversation_id,
                tool_name=tool_name,
                arguments=arguments,
                reason=decision.reason,
            )
            await self._record_call(
                session,
                user_id=user.id,
                conversation_id=context.conversation_id,
                message_id=context.message_id,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                status="PENDING_CONFIRMATION",
                error=None,
                autonomy_level=decision.user_autonomy_level,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            return ToolInvokeOut(
                status="PENDING_CONFIRMATION",
                tool_name=tool_name,
                pending_action_id=pending.id,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        # 4. Validar argumentos
        validation_error = _validate_arguments(tool.manifest.parameters, arguments)
        if validation_error is not None:
            await self._record_call(
                session,
                user_id=user.id,
                conversation_id=context.conversation_id,
                message_id=context.message_id,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                status="ERROR",
                error=f"argumentos inválidos: {validation_error}",
                autonomy_level=decision.user_autonomy_level,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            return ToolInvokeOut(
                status="ERROR",
                tool_name=tool_name,
                error=f"argumentos inválidos: {validation_error}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        # 5. Ejecutar
        return await self._execute_and_record(
            session,
            tool=tool,
            user_id=user.id,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            tool_name=tool_name,
            arguments=arguments,
            autonomy_level=decision.user_autonomy_level,
            started=started,
        )

    async def execute_pending(
        self,
        session: AsyncSession,
        *,
        pending: PendingAction,
        user: User,
    ) -> ToolInvokeOut:
        """Ejecuta un PendingAction ya confirmado por el usuario."""
        started = time.perf_counter()
        tool = self.registry.get(pending.tool_name)

        if tool is None:
            pending.status = "REJECTED"
            pending.error = f"tool desconocida: {pending.tool_name}"
            return ToolInvokeOut(
                status="DENIED",
                tool_name=pending.tool_name,
                error=pending.error,
            )

        result = await self._execute_and_record(
            session,
            tool=tool,
            user_id=user.id,
            conversation_id=pending.conversation_id,
            message_id=None,
            tool_name=pending.tool_name,
            arguments=pending.arguments or {},
            autonomy_level=4,  # el usuario ya confirmó; equivale a nivel 4
            started=started,
        )

        pending.status = "CONFIRMED" if result.status == "OK" else "REJECTED"
        pending.result = _truncate(result.result)
        pending.error = result.error
        return result

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _execute_and_record(
        self,
        session: AsyncSession,
        *,
        tool,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        tool_name: str,
        arguments: dict[str, Any],
        autonomy_level: int,
        started: float,
    ) -> ToolInvokeOut:
        tool_context = ToolContext(
            user_id=user_id,
            conversation_id=conversation_id,
            autonomy_level=autonomy_level,
        )
        timeout_s = tool.manifest.timeout_ms / 1000.0
        status_str = "OK"
        result: Any = None
        error: str | None = None

        try:
            result = await asyncio.wait_for(
                tool.execute(arguments, tool_context),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            status_str = "TIMEOUT"
            error = f"timeout tras {tool.manifest.timeout_ms} ms"
        except ToolExecutionError as exc:
            status_str = "ERROR"
            error = str(exc)
        except Exception as exc:
            log.warning(
                "tool_execution_unexpected_error",
                tool=tool_name,
                error=str(exc),
            )
            status_str = "ERROR"
            error = f"error inesperado: {exc}"

        latency_ms = int((time.perf_counter() - started) * 1000)

        await self._record_call(
            session,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            tool_name=tool_name,
            arguments=arguments,
            result=_truncate(result),
            status=status_str,
            error=error,
            autonomy_level=autonomy_level,
            latency_ms=latency_ms,
        )

        return ToolInvokeOut(
            status=status_str,  # type: ignore[arg-type]
            tool_name=tool_name,
            result=result,
            error=error,
            latency_ms=latency_ms,
        )

    async def _record_call(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        status: str,
        error: str | None,
        autonomy_level: int,
        latency_ms: int,
    ) -> None:
        session.add(
            ToolCall(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                status=status,
                error=(error[:2000] if error else None),
                autonomy_level=autonomy_level,
                latency_ms=latency_ms,
            )
        )
        await session.flush()

    async def _create_pending(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
    ) -> PendingAction:
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=DEFAULT_PENDING_TTL_MINUTES
        )
        pending = PendingAction(
            user_id=user_id,
            conversation_id=conversation_id,
            tool_name=tool_name,
            arguments=arguments,
            status="PENDING",
            reason=reason,
            expires_at=expires_at,
        )
        session.add(pending)
        await session.flush()
        return pending


# --------------------------------------------------------------------------- #
# Instancia global
# --------------------------------------------------------------------------- #
_runtime: ToolRuntime | None = None


def build_runtime() -> ToolRuntime:
    global _runtime
    if _runtime is not None:
        return _runtime
    from app.tools.registry import build_registry

    _runtime = ToolRuntime(build_registry())
    return _runtime