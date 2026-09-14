"""Tests del sistema de settings dinámicos.

Cubren:
  - Fallback a defaults cuando no hay override.
  - Override prioritario sobre el default.
  - Invalidación de caché tras un cambio.
  - Listado con metadata.
  - Borrado (vuelve al default).
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import dynamic
from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_cache():
    """Limpia la caché antes y después de cada test."""
    dynamic.invalidate_dynamic_cache()
    yield
    dynamic.invalidate_dynamic_cache()


@pytest.mark.asyncio
async def test_default_when_no_override():
    """Sin override, get_dynamic devuelve el default del código."""
    value = await dynamic.get_dynamic("memory_top_k")
    assert value == get_settings().memory_top_k


@pytest.mark.asyncio
async def test_override_takes_precedence(session: AsyncSession):
    await dynamic.set_dynamic_setting(
        "memory_top_k", 99, category="memory"
    )
    # Invalidación ya ocurre dentro de set_dynamic_setting
    value = await dynamic.get_dynamic("memory_top_k")
    assert value == 99


@pytest.mark.asyncio
async def test_delete_reverts_to_default(session: AsyncSession):
    await dynamic.set_dynamic_setting("memory_top_k", 99)
    assert await dynamic.get_dynamic("memory_top_k") == 99

    deleted = await dynamic.delete_dynamic_setting("memory_top_k")
    assert deleted is True

    value = await dynamic.get_dynamic("memory_top_k")
    assert value == get_settings().memory_top_k


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false(session: AsyncSession):
    ok = await dynamic.delete_dynamic_setting("clave_que_no_existe")
    assert ok is False


@pytest.mark.asyncio
async def test_unknown_key_with_explicit_default():
    value = await dynamic.get_dynamic("clave_desconocida", default="fallback")
    assert value == "fallback"


@pytest.mark.asyncio
async def test_unknown_key_without_default():
    value = await dynamic.get_dynamic("clave_desconocida")
    assert value is None


@pytest.mark.asyncio
async def test_get_many(session: AsyncSession):
    await dynamic.set_dynamic_setting("memory_top_k", 42)
    values = await dynamic.get_many_dynamic(
        ["memory_top_k", "rag_top_k", "llm_provider"]
    )
    assert values["memory_top_k"] == 42
    assert values["rag_top_k"] == get_settings().rag_top_k
    assert values["llm_provider"] == get_settings().llm_provider


@pytest.mark.asyncio
async def test_list_all_includes_defaults_and_overrides(session: AsyncSession):
    await dynamic.set_dynamic_setting("memory_top_k", 7)
    items = await dynamic.list_all_settings_with_metadata()
    by_key = {i["key"]: i for i in items}
    assert "memory_top_k" in by_key
    assert by_key["memory_top_k"]["is_override"] is True
    assert by_key["memory_top_k"]["value"] == 7
    assert by_key["memory_top_k"]["default"] == get_settings().memory_top_k
    # Una clave sin override muestra is_override False
    assert by_key["rag_top_k"]["is_override"] is False


@pytest.mark.asyncio
async def test_set_twice_updates(session: AsyncSession):
    await dynamic.set_dynamic_setting("memory_top_k", 1)
    await dynamic.set_dynamic_setting("memory_top_k", 2)
    assert await dynamic.get_dynamic("memory_top_k") == 2