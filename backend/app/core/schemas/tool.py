from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ToolStatus = Literal["OK", "ERROR", "TIMEOUT", "DENIED", "PENDING_CONFIRMATION"]
PendingStatus = Literal["PENDING", "CONFIRMED", "REJECTED", "EXPIRED"]


class ToolManifest(BaseModel):
    """Declaración de una herramienta.

    Es el contrato que cada tool debe exponer. Se registra en memoria
    (Registry) y se sincroniza con la tabla `tools` para que los admins
    puedan consultarla y, opcionalmente, desactivarla.
    """

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=3, max_length=1000)

    # JSON Schema de los parámetros aceptados. Ejemplo:
    # {
    #   "type": "object",
    #   "properties": {"expression": {"type": "string"}},
    #   "required": ["expression"],
    # }
    parameters: dict[str, Any] = Field(default_factory=dict)

    # Códigos de permiso requeridos (contra el rol del usuario).
    required_permissions: list[str] = Field(default_factory=list)

    # Nivel mínimo de autonomía del usuario (0-4).
    min_autonomy_level: int = Field(default=0, ge=0, le=4)

    # Si True, el runtime crea un PendingAction en vez de ejecutar.
    requires_confirmation: bool = False

    # Timeout duro. El runtime lo aplica con asyncio.wait_for.
    timeout_ms: int = Field(default=10_000, ge=100, le=300_000)

    # Si False, la tool está registrada pero bloqueada a nivel global.
    enabled: bool = True

    scope: Literal["builtin", "user", "org"] = "builtin"


class ToolOut(BaseModel):
    """Vista pública de una tool."""
    name: str
    description: str
    scope: str
    required_permissions: list[str]
    min_autonomy_level: int
    requires_confirmation: bool
    timeout_ms: int
    enabled: bool

    @classmethod
    def from_manifest(cls, m: ToolManifest) -> "ToolOut":
        return cls(
            name=m.name,
            description=m.description,
            scope=m.scope,
            required_permissions=list(m.required_permissions),
            min_autonomy_level=m.min_autonomy_level,
            requires_confirmation=m.requires_confirmation,
            timeout_ms=m.timeout_ms,
            enabled=m.enabled,
        )


class ToolCallOut(BaseModel):
    """Vista pública de una llamada a tool (auditoría)."""
    id: uuid.UUID
    tool_name: str
    status: str
    arguments: dict
    result: Any | None
    error: str | None
    autonomy_level: int
    latency_ms: int
    created_at: datetime

    @classmethod
    def from_model(cls, c) -> "ToolCallOut":
        return cls(
            id=c.id,
            tool_name=c.tool_name,
            status=c.status,
            arguments=c.arguments or {},
            result=c.result,
            error=c.error,
            autonomy_level=c.autonomy_level,
            latency_ms=c.latency_ms,
            created_at=c.created_at,
        )


class PendingActionOut(BaseModel):
    """Vista pública de una acción pendiente de confirmación."""
    id: uuid.UUID
    tool_name: str
    arguments: dict
    status: str
    reason: str | None
    expires_at: datetime
    result: Any | None
    error: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, p) -> "PendingActionOut":
        return cls(
            id=p.id,
            tool_name=p.tool_name,
            arguments=p.arguments or {},
            status=p.status,
            reason=p.reason,
            expires_at=p.expires_at,
            result=p.result,
            error=p.error,
            created_at=p.created_at,
        )


class ToolInvokeIn(BaseModel):
    """Body del endpoint POST /tools/{name}/invoke."""
    arguments: dict[str, Any] = Field(default_factory=dict)
    conversation_id: uuid.UUID | None = None


class ToolInvokeOut(BaseModel):
    """Respuesta del endpoint invoke."""
    status: ToolStatus
    tool_name: str
    result: Any | None = None
    error: str | None = None
    latency_ms: int = 0
    # Si status == PENDING_CONFIRMATION, este es el id de la acción.
    pending_action_id: uuid.UUID | None = None