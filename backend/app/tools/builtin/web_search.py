"""Tool: búsqueda web vía Tavily.

Política:
  - Requiere `TAVILY_API_KEY` en settings. Sin key, la tool existe pero
    devuelve un error explícito (así el LLM sabe que no está disponible).
  - Rechaza queries muy cortas o muy largas.
  - Máximo `max_results` (default 5, tope 10).
  - Timeout 15s.

Nivel de autonomía mínimo: 3.

Endpoints Tavily usados:
  POST https://api.tavily.com/search
  Body: {"api_key": "...", "query": "...", "max_results": N}
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config.settings import get_settings
from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.core.schemas.tool import ToolManifest


_TAVILY_ENDPOINT = "https://api.tavily.com/search"


class WebSearchTool:
    manifest = ToolManifest(
        name="web_search",
        description=(
            "Busca información actual en internet. Devuelve una lista de "
            "resultados con título, URL y un fragmento de texto."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta de búsqueda",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número de resultados (1-10, default 5)",
                },
            },
            "required": ["query"],
        },
        required_permissions=[],
        min_autonomy_level=3,
        requires_confirmation=False,
        timeout_ms=15_000,
        enabled=True,
        scope="builtin",
    )

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Inyectable para tests con httpx.MockTransport
        self._transport = transport

    async def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolExecutionError("se requiere 'query' como string no vacío")
        query = query.strip()
        if len(query) < 2:
            raise ToolExecutionError("la query es demasiado corta")
        if len(query) > 500:
            raise ToolExecutionError("la query excede 500 caracteres")

        raw_max = arguments.get("max_results", 5)
        try:
            max_results = int(raw_max)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError("max_results debe ser un entero") from exc
        max_results = max(1, min(10, max_results))

        settings = get_settings()
        api_key = settings.tavily_api_key
        if not api_key:
            raise ToolExecutionError(
                "web_search no está configurado en este entorno "
                "(falta TAVILY_API_KEY)"
            )

        body = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": True,
            "include_raw_content": False,
        }

        timeout = httpx.Timeout(
            connect=5.0,
            read=float(settings.web_fetch_timeout_s),
            write=5.0,
            pool=5.0,
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
            ) as client:
                r = await client.post(_TAVILY_ENDPOINT, json=body)
        except httpx.TimeoutException as exc:
            raise ToolExecutionError("timeout en la búsqueda web") from exc
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"error de red: {exc}") from exc

        if r.status_code != 200:
            raise ToolExecutionError(
                f"búsqueda falló: HTTP {r.status_code}"
            )

        try:
            payload = r.json()
        except ValueError as exc:
            raise ToolExecutionError("respuesta no es JSON válido") from exc

        raw_results = payload.get("results") or []
        results = []
        for item in raw_results[:max_results]:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": (item.get("content") or "")[:500],
                }
            )

        return {
            "query": query,
            "count": len(results),
            "answer": payload.get("answer") or "",
            "results": results,
        }