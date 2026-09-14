"""Tool: descarga una URL y devuelve el texto plano.

Política de seguridad:
  - Solo http/https.
  - Rechaza IPs privadas y localhost (SSRF básico). Esto protege a la
    infra donde corre ELI de exponer servicios internos al LLM.
  - Limita tamaño de respuesta (settings.web_fetch_max_bytes).
  - Sigue máximo 3 redirects.
  - Timeout configurable.
  - Del HTML extrae texto plano (con html.parser de stdlib).

Nivel de autonomía mínimo: 3.
"""
from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config.settings import get_settings
from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.core.schemas.tool import ToolManifest


class _TextExtractor(HTMLParser):
    """Extrae texto plano de HTML. Ignora scripts, styles y comentarios."""

    _SKIP = {"script", "style", "noscript", "head", "iframe", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag.lower() in ("p", "div", "br", "li", "tr"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def text(self) -> str:
        # Colapsar espacios y líneas múltiples
        raw = " ".join(self._parts)
        # Cada "\n" que añadimos pierde sentido tras el join; reconstruimos
        # colapsando espacios múltiples y añadiendo saltos por bloques.
        import re
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw


def _is_public_host(hostname: str) -> bool:
    """True si el host no es local ni privado.

    Resuelve el hostname para detectar IPs privadas tras un DNS. Esto no es
    bulletproof (DNS rebinding), pero filtra el 99% de los ataques SSRF
    casuales.
    """
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


class WebFetchTool:
    manifest = ToolManifest(
        name="web_fetch",
        description=(
            "Descarga el contenido de una URL http(s) y devuelve el texto "
            "plano (sin HTML). Útil para leer una página concreta."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL http(s) a descargar",
                }
            },
            "required": ["url"],
        },
        required_permissions=[],
        min_autonomy_level=3,
        requires_confirmation=False,
        timeout_ms=20_000,
        enabled=True,
        scope="builtin",
    )

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Inyectable para tests con httpx.MockTransport
        self._transport = transport

    async def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ToolExecutionError("se requiere 'url' como string no vacío")
        url = url.strip()

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ToolExecutionError("solo se permiten URLs http o https")
        if not parsed.hostname:
            raise ToolExecutionError("URL sin host")
        if not _is_public_host(parsed.hostname):
            raise ToolExecutionError(
                "URL apunta a una dirección privada o local (bloqueado por seguridad)"
            )

        settings = get_settings()
        timeout = httpx.Timeout(
            connect=5.0,
            read=float(settings.web_fetch_timeout_s),
            write=5.0,
            pool=5.0,
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                max_redirects=3,
                transport=self._transport,
                headers={"User-Agent": "ELI/0.1 (+https://eli.local)"},
            ) as client:
                r = await client.get(url)
        except httpx.TimeoutException as exc:
            raise ToolExecutionError(f"timeout al descargar {url}") from exc
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"error de red: {exc}") from exc

        if r.status_code >= 400:
            raise ToolExecutionError(
                f"HTTP {r.status_code} al descargar {url}"
            )

        # Límite de tamaño
        content = r.content
        if len(content) > settings.web_fetch_max_bytes:
            raise ToolExecutionError(
                f"respuesta excede {settings.web_fetch_max_bytes} bytes"
            )

        content_type = r.headers.get("content-type", "").lower()
        if "html" in content_type or "<html" in content[:200].decode(
            "utf-8", errors="ignore"
        ).lower():
            parser = _TextExtractor()
            try:
                parser.feed(content.decode(r.encoding or "utf-8", errors="replace"))
            except Exception:
                # Fallback: decodificar sin parser
                return {
                    "url": str(r.url),
                    "status": r.status_code,
                    "content_type": content_type,
                    "text": content.decode("utf-8", errors="replace")[:10_000],
                }
            text = parser.text()
        else:
            # Texto plano, JSON, XML → devolver tal cual
            text = content.decode(r.encoding or "utf-8", errors="replace")

        return {
            "url": str(r.url),
            "status": r.status_code,
            "content_type": content_type,
            "text": text[:10_000],
            "truncated": len(text) > 10_000,
        }