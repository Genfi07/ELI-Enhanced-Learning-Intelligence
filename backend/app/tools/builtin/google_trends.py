"""Tool: consulta Google Trends vía pytrends.

Devuelve la serie temporal de interés de una keyword y las queries
relacionadas (top + rising). Útil para detectar tendencias y picos
de interés.

pytrends no es oficial; puede fallar si Google cambia sus endpoints.
En ese caso la tool devuelve un error explícito y ELI lo comunica.

Nivel de autonomía mínimo: 3.
"""
from __future__ import annotations

import asyncio
import warnings
from typing import Any

from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.core.schemas.tool import ToolManifest


_ALLOWED_TIMEFRAMES = {
    "now 1-H",
    "now 4-H",
    "now 1-d",
    "now 7-d",
    "today 1-m",
    "today 3-m",
    "today 12-m",
    "today 5-y",
}


def _run_trends(keyword: str, timeframe: str, geo: str) -> dict[str, Any]:
    """Trabajo bloqueante: se ejecuta en un thread separado."""
    from pytrends.request import TrendReq

    warnings.filterwarnings("ignore")

    p = TrendReq(hl="es-ES", tz=-180)
    p.build_payload([keyword], timeframe=timeframe, geo=geo)

    df = p.interest_over_time()
    series: list[dict[str, Any]] = []
    if df is not None and not df.empty:
        for ts, row in df.iterrows():
            series.append(
                {
                    "date": ts.isoformat(),
                    "value": int(row.get(keyword, 0)),
                }
            )

    related: dict[str, list[dict[str, Any]]] = {
        "top": [],
        "rising": [],
    }
    try:
        rel = p.related_queries()
        bucket = rel.get(keyword) or {}
        for key in ("top", "rising"):
            data = bucket.get(key)
            if data is None:
                continue
            try:
                rows = data.to_dict("records")
            except Exception:
                rows = []
            for r in rows[:10]:
                related[key].append(
                    {
                        "query": str(r.get("query", "")),
                        "value": int(r.get("value", 0) or 0),
                    }
                )
    except Exception:
        # related_queries a veces falla; no es crítico
        pass

    return {
        "keyword": keyword,
        "timeframe": timeframe,
        "geo": geo or "worldwide",
        "series": series,
        "related": related,
    }


class GoogleTrendsTool:
    manifest = ToolManifest(
        name="google_trends",
        description=(
            "Consulta Google Trends para una keyword. Devuelve la evolución "
            "del interés en el tiempo y las búsquedas relacionadas (top y "
            "rising). Útil para ver qué está ganando popularidad."
        ),
        parameters={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Término a consultar",
                },
                "timeframe": {
                    "type": "string",
                    "description": (
                        "Ventana temporal: now 7-d | today 1-m | "
                        "today 3-m | today 12-m | today 5-y"
                    ),
                },
                "geo": {
                    "type": "string",
                    "description": "Código de país ISO-2 (ej. ES, MX, US). Vacío = mundial.",
                },
            },
            "required": ["keyword"],
        },
        required_permissions=[],
        min_autonomy_level=3,
        requires_confirmation=False,
        timeout_ms=20_000,
        enabled=True,
        scope="builtin",
    )

    async def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        keyword = arguments.get("keyword")
        if not isinstance(keyword, str) or not keyword.strip():
            raise ToolExecutionError("se requiere 'keyword' como string no vacío")
        keyword = keyword.strip()
        if len(keyword) < 2:
            raise ToolExecutionError("la keyword es demasiado corta")
        if len(keyword) > 100:
            raise ToolExecutionError("la keyword excede 100 caracteres")

        timeframe = arguments.get("timeframe", "today 3-m")
        if timeframe not in _ALLOWED_TIMEFRAMES:
            timeframe = "today 3-m"

        geo = arguments.get("geo", "") or ""
        if geo and (len(geo) != 2 or not geo.isalpha()):
            geo = ""
        geo = geo.upper()

        try:
            result = await asyncio.to_thread(_run_trends, keyword, timeframe, geo)
        except ImportError as exc:
            raise ToolExecutionError(
                "pytrends no está instalado en el backend"
            ) from exc
        except Exception as exc:
            raise ToolExecutionError(
                f"Google Trends falló: {exc}"
            ) from exc

        return result