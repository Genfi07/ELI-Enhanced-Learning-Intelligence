"""Registry de herramientas.

Diseño:
  - El registry vive en memoria con los manifests de las tools disponibles.
  - Al arrancar, sincroniza con la tabla `tools`: inserta los que no existan,
    actualiza descripción/params de los que sí. NO sobreescribe `enabled`
    para no pisar decisiones de un admin.
  - `is_enabled_in_db` es PERMISIVO: si la tool no está en BD, se asume
    habilitada. La tabla es un override del admin, no la fuente de verdad.
  - Los nombres son únicos. Registrar dos tools con el mismo nombre lanza.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.contracts.tool import Tool
from app.core.schemas.tool import ToolManifest
from app.db.models.tool import Tool as ToolModel
from app.db.session import session_scope
from app.observability.logging import get_logger

log = get_logger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------ #
    # Gestión en memoria
    # ------------------------------------------------------------------ #
    def register(self, tool: Tool) -> None:
        name = tool.manifest.name
        if name in self._tools:
            raise ValueError(f"tool duplicada: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all_manifests(self) -> list[ToolManifest]:
        return [t.manifest for t in self._tools.values()]

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    # ------------------------------------------------------------------ #
    # Sincronización con BD
    # ------------------------------------------------------------------ #
    async def sync_to_db(self) -> None:
        """Sincroniza los manifests en memoria con la tabla `tools`.

        Idempotente:
          - Inserta tools nuevas.
          - Actualiza descripción, schema, permisos, timeout, etc.
          - NUNCA toca `enabled` en updates (respetamos la decisión del admin).
        """
        async with session_scope() as session:
            for tool in self._tools.values():
                manifest = tool.manifest
                existing = await session.scalar(
                    select(ToolModel).where(ToolModel.name == manifest.name)
                )
                if existing is None:
                    session.add(
                        ToolModel(
                            name=manifest.name,
                            description=manifest.description,
                            scope=manifest.scope,
                            parameters_schema=manifest.parameters,
                            required_permissions=manifest.required_permissions,
                            min_autonomy_level=manifest.min_autonomy_level,
                            requires_confirmation=manifest.requires_confirmation,
                            timeout_ms=manifest.timeout_ms,
                            enabled=manifest.enabled,
                            meta={},
                        )
                    )
                else:
                    existing.description = manifest.description
                    existing.parameters_schema = manifest.parameters
                    existing.required_permissions = manifest.required_permissions
                    existing.min_autonomy_level = manifest.min_autonomy_level
                    existing.requires_confirmation = manifest.requires_confirmation
                    existing.timeout_ms = manifest.timeout_ms
                    existing.scope = manifest.scope
                    # OJO: NO tocamos existing.enabled — es decisión del admin

        log.info("tools_synced", count=len(self._tools))

    async def is_enabled_in_db(self, name: str) -> bool:
        """Consulta la tabla para ver si un admin ha desactivado la tool.

        Semántica:
          - Si la fila no existe → True (aún no sincronizada; usar manifest).
          - Si existe con enabled=True → True.
          - Si existe con enabled=False → False.
        """
        async with session_scope() as session:
            row = await session.scalar(
                select(ToolModel).where(ToolModel.name == name)
            )
            if row is None:
                return True
            return bool(row.enabled)


# --------------------------------------------------------------------------- #
# Instancia global + builder
# --------------------------------------------------------------------------- #
_registry: ToolRegistry | None = None


def build_registry() -> ToolRegistry:
    """Construye el registry con todas las builtin tools registradas."""
    global _registry
    if _registry is not None:
        return _registry

    from app.tools.builtin.calculator import CalculatorTool
    from app.tools.builtin.datetime_tool import DatetimeTool
    from app.tools.builtin.web_fetch import WebFetchTool
    from app.tools.builtin.web_search import WebSearchTool

    reg = ToolRegistry()
    reg.register(CalculatorTool())
    reg.register(DatetimeTool())
    reg.register(WebFetchTool())
    reg.register(WebSearchTool())

    _registry = reg
    return reg