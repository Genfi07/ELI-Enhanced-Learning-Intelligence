"""Tool: fecha/hora actual y operaciones básicas de tiempo.

Soporta:
  - mode="now"      → fecha/hora actual en la zona indicada (o UTC)
  - mode="diff"     → diferencia entre dos fechas ISO 8601 (en segundos)
  - mode="add"      → suma días/horas/minutos/segundos a una fecha base

Sin dependencias externas. Usa `zoneinfo` (stdlib) para zonas horarias.

Nivel de autonomía mínimo: 2.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.core.schemas.tool import ToolManifest


class DatetimeTool:
    manifest = ToolManifest(
        name="datetime",
        description=(
            "Devuelve la fecha/hora actual, calcula diferencias entre fechas, "
            "o suma intervalos a una fecha. Usa ISO 8601 para las fechas."
        ),
        parameters={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "now | diff | add",
                },
                "timezone": {
                    "type": "string",
                    "description": "Zona horaria IANA (ej: Europe/Madrid). Default: UTC",
                },
                "date_a": {
                    "type": "string",
                    "description": "Primera fecha ISO 8601 (para mode=diff)",
                },
                "date_b": {
                    "type": "string",
                    "description": "Segunda fecha ISO 8601 (para mode=diff)",
                },
                "base": {
                    "type": "string",
                    "description": "Fecha base ISO 8601 (para mode=add)",
                },
                "days": {"type": "integer"},
                "hours": {"type": "integer"},
                "minutes": {"type": "integer"},
                "seconds": {"type": "integer"},
            },
            "required": ["mode"],
        },
        required_permissions=[],
        min_autonomy_level=2,
        requires_confirmation=False,
        timeout_ms=2_000,
        enabled=True,
        scope="builtin",
    )

    async def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        mode = arguments.get("mode")
        if mode not in ("now", "diff", "add"):
            raise ToolExecutionError(
                "mode debe ser 'now', 'diff' o 'add'"
            )

        tz_name = arguments.get("timezone") or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ToolExecutionError(f"zona horaria desconocida: {tz_name}") from exc

        if mode == "now":
            now = datetime.now(tz)
            return {
                "iso": now.isoformat(),
                "unix": int(now.timestamp()),
                "timezone": tz_name,
                "weekday": now.strftime("%A"),
            }

        if mode == "diff":
            a = self._parse_iso(arguments.get("date_a"), tz)
            b = self._parse_iso(arguments.get("date_b"), tz)
            delta = b - a
            return {
                "seconds": int(delta.total_seconds()),
                "days": delta.days,
                "human": self._human_delta(delta),
            }

        # mode == "add"
        base = self._parse_iso(arguments.get("base"), tz)
        delta = timedelta(
            days=int(arguments.get("days") or 0),
            hours=int(arguments.get("hours") or 0),
            minutes=int(arguments.get("minutes") or 0),
            seconds=int(arguments.get("seconds") or 0),
        )
        result = base + delta
        return {
            "iso": result.isoformat(),
            "unix": int(result.timestamp()),
            "added": {
                "days": delta.days,
                "seconds": delta.seconds,
            },
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_iso(value: Any, tz: ZoneInfo) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ToolExecutionError("se requiere una fecha ISO 8601")
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ToolExecutionError(f"fecha inválida: {value}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt

    @staticmethod
    def _human_delta(delta: timedelta) -> str:
        total = int(abs(delta.total_seconds()))
        sign = "antes" if delta.total_seconds() < 0 else "después"
        days = total // 86400
        hours = (total % 86400) // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
        return f"{' '.join(parts)} {sign}"