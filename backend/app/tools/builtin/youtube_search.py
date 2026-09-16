"""Tool: búsqueda de videos en YouTube vía Data API v3.

Devuelve los últimos videos que mejor matchean la query. Permite ordenar
por relevancia, fecha o número de vistas.

Requiere YOUTUBE_API_KEY en settings. Sin key, la tool existe pero
devuelve un error explícito.

Nivel de autonomía mínimo: 3.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config.settings import get_settings
from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.core.schemas.tool import ToolManifest


_YT_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"

_ALLOWED_ORDERS = {"relevance", "date", "viewCount", "rating", "title"}


class YouTubeSearchTool:
    manifest = ToolManifest(
        name="youtube_search",
        description=(
            "Busca videos en YouTube. Devuelve título, canal, fecha de "
            "publicación, URL y descripción corta. Útil para encontrar "
            "contenido reciente de creadores sobre un tema."
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
                    "description": "Número de resultados (1-15, default 5)",
                },
                "order": {
                    "type": "string",
                    "description": (
                        "Orden: relevance | date | viewCount | rating | title"
                    ),
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
        max_results = max(1, min(15, max_results))

        order = arguments.get("order", "relevance")
        if order not in _ALLOWED_ORDERS:
            order = "relevance"

        settings = get_settings()
        api_key = settings.youtube_api_key
        if not api_key:
            raise ToolExecutionError(
                "youtube_search no está configurado en este entorno "
                "(falta YOUTUBE_API_KEY)"
            )

        params = {
            "part": "snippet",
            "q": query,
            "maxResults": max_results,
            "type": "video",
            "order": order,
            "key": api_key,
        }

        timeout = httpx.Timeout(
            connect=5.0,
            read=15.0,
            write=5.0,
            pool=5.0,
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
            ) as client:
                r = await client.get(_YT_ENDPOINT, params=params)
        except httpx.TimeoutException as exc:
            raise ToolExecutionError("timeout en la búsqueda de YouTube") from exc
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"error de red: {exc}") from exc

        if r.status_code != 200:
            # Intentar extraer el mensaje de error de Google
            try:
                err = r.json().get("error", {})
                msg = err.get("message", f"HTTP {r.status_code}")
            except Exception:
                msg = f"HTTP {r.status_code}"
            raise ToolExecutionError(f"búsqueda en YouTube falló: {msg}")

        try:
            payload = r.json()
        except ValueError as exc:
            raise ToolExecutionError("respuesta de YouTube no es JSON válido") from exc

        raw_items = payload.get("items") or []
        results = []
        for item in raw_items[:max_results]:
            snippet = item.get("snippet") or {}
            vid = (item.get("id") or {}).get("videoId")
            if not vid:
                continue
            results.append(
                {
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "description": (snippet.get("description") or "")[:300],
                    "url": f"https://www.youtube.com/watch?v={vid}",
                }
            )

        return {
            "query": query,
            "order": order,
            "count": len(results),
            "results": results,
        }