"""Tests de web_fetch y web_search con httpx.MockTransport."""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.tools.builtin.web_fetch import WebFetchTool
from app.tools.builtin.web_search import WebSearchTool


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(
        user_id=uuid.uuid4(),
        conversation_id=None,
        autonomy_level=3,
    )


# --------------------------------------------------------------------------- #
# web_fetch
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_fetch_plain_text(ctx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"contenido plano de prueba",
        )

    tool = WebFetchTool(transport=httpx.MockTransport(handler))
    res = await tool.execute({"url": "https://example.com/x.txt"}, ctx)
    assert res["status"] == 200
    assert "contenido plano" in res["text"]


@pytest.mark.asyncio
async def test_fetch_html_extracts_text(ctx):
    def handler(request: httpx.Request) -> httpx.Response:
        html = """
        <html>
          <head><style>body{color:red}</style><script>alert(1)</script></head>
          <body>
            <h1>Título</h1>
            <p>Párrafo con contenido.</p>
            <p>Otro párrafo.</p>
          </body>
        </html>
        """
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=html.encode("utf-8"),
        )

    tool = WebFetchTool(transport=httpx.MockTransport(handler))
    res = await tool.execute({"url": "https://example.com/"}, ctx)
    # El script y el style NO deben aparecer
    assert "alert" not in res["text"]
    assert "color:red" not in res["text"]
    # El contenido sí
    assert "Título" in res["text"]
    assert "Párrafo con contenido" in res["text"]


@pytest.mark.asyncio
async def test_fetch_http_error(ctx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found")

    tool = WebFetchTool(transport=httpx.MockTransport(handler))
    with pytest.raises(ToolExecutionError) as exc:
        await tool.execute({"url": "https://example.com/missing"}, ctx)
    assert "404" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_rejects_private_hosts(ctx):
    tool = WebFetchTool()
    for url in (
        "http://localhost/admin",
        "http://127.0.0.1/secret",
        "http://192.168.1.1/router",
        "http://10.0.0.1/",
    ):
        with pytest.raises(ToolExecutionError) as exc:
            await tool.execute({"url": url}, ctx)
        assert (
            "privada" in str(exc.value).lower()
            or "seguridad" in str(exc.value).lower()
        )


@pytest.mark.asyncio
async def test_fetch_rejects_non_http_scheme(ctx):
    tool = WebFetchTool()
    with pytest.raises(ToolExecutionError):
        await tool.execute({"url": "file:///etc/passwd"}, ctx)
    with pytest.raises(ToolExecutionError):
        await tool.execute({"url": "ftp://example.com"}, ctx)


@pytest.mark.asyncio
async def test_fetch_rejects_empty_url(ctx):
    tool = WebFetchTool()
    with pytest.raises(ToolExecutionError):
        await tool.execute({"url": ""}, ctx)
    with pytest.raises(ToolExecutionError):
        await tool.execute({}, ctx)


# --------------------------------------------------------------------------- #
# web_search
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_search_without_api_key(ctx, monkeypatch):
    """Sin TAVILY_API_KEY, la tool debe devolver un error claro."""
    from app.config.settings import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "tavily_api_key", None)

    tool = WebSearchTool()
    with pytest.raises(ToolExecutionError) as exc:
        await tool.execute({"query": "python async"}, ctx)
    assert "no está configurado" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_search_returns_results(ctx, monkeypatch):
    from app.config.settings import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "tavily_api_key", "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.tavily.com"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "R1", "url": "https://a.com", "content": "Snippet 1"},
                    {"title": "R2", "url": "https://b.com", "content": "Snippet 2"},
                ]
            },
        )

    tool = WebSearchTool(transport=httpx.MockTransport(handler))
    res = await tool.execute({"query": "algo", "max_results": 2}, ctx)
    assert res["count"] == 2
    assert res["results"][0]["title"] == "R1"
    assert res["results"][1]["url"] == "https://b.com"


@pytest.mark.asyncio
async def test_search_caps_max_results(ctx, monkeypatch):
    """max_results=999 debe sanearse a un valor <= 10 antes de enviar a Tavily."""
    from app.config.settings import get_settings
    monkeypatch.setattr(get_settings(), "tavily_api_key", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # El handler comprueba que el saneamiento se ha aplicado
        assert body["max_results"] <= 10
        return httpx.Response(200, json={"results": []})

    tool = WebSearchTool(transport=httpx.MockTransport(handler))
    # Query suficientemente larga para pasar la validación (>=2 chars)
    res = await tool.execute(
        {"query": "python async", "max_results": 999}, ctx
    )
    assert res["count"] == 0


@pytest.mark.asyncio
async def test_search_rejects_empty_query(ctx, monkeypatch):
    from app.config.settings import get_settings
    monkeypatch.setattr(get_settings(), "tavily_api_key", "k")

    tool = WebSearchTool()
    with pytest.raises(ToolExecutionError):
        await tool.execute({"query": ""}, ctx)


@pytest.mark.asyncio
async def test_search_http_error(ctx, monkeypatch):
    from app.config.settings import get_settings
    monkeypatch.setattr(get_settings(), "tavily_api_key", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    tool = WebSearchTool(transport=httpx.MockTransport(handler))
    with pytest.raises(ToolExecutionError) as exc:
        await tool.execute({"query": "algo"}, ctx)
    assert "500" in str(exc.value)