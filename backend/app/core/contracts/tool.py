"""Contrato que debe cumplir cada herramienta.

Una tool es una función async que recibe argumentos y devuelve un resultado
JSON-serializable. El runtime se encarga de: autorización, timeout, auditoría,
y (si aplica) confirmación previa.

Reglas para implementar una tool:
  - `manifest` es una propiedad de clase que describe la tool.
  - `execute(arguments, context)` es async y NUNCA lanza por errores de negocio;
    devuelve un resultado o lanza ToolExecutionError para errores reales.
  - Los argumentos se validan contra `manifest.parameters` (JSON Schema) ANTES
    de llamar a execute. Si no cumplen, el runtime no invoca.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.schemas.tool import ToolManifest


class ToolError(RuntimeError):
    """Error genérico de una tool."""


class ToolExecutionError(ToolError):
    """Fallo durante la ejecución de una tool."""


class ToolValidationError(ToolError):
    """Los argumentos no cumplen el JSON Schema."""


@dataclass
class ToolContext:
    """Contexto de ejecución que el runtime entrega a cada tool."""
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None
    autonomy_level: int
    # Permite a la tool leer settings y logs, no es obligatorio usarlos.


class Tool(Protocol):
    manifest: ToolManifest

    async def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> Any: ...