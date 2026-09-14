"""Tests del RateLimiter (funciones puras, sin HTTP)."""
from __future__ import annotations

import asyncio

import pytest

from app.security.rate_limit import RateLimiter, get_limiter


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter()


@pytest.mark.asyncio
async def test_allows_up_to_limit(limiter):
    for _ in range(5):
        ok, _ = await limiter.check_and_record("k", limit=5, window_seconds=60)
        assert ok is True


@pytest.mark.asyncio
async def test_blocks_above_limit(limiter):
    for _ in range(3):
        ok, _ = await limiter.check_and_record("k", limit=3, window_seconds=60)
        assert ok is True

    ok, retry = await limiter.check_and_record("k", limit=3, window_seconds=60)
    assert ok is False
    assert retry > 0


@pytest.mark.asyncio
async def test_window_expires(limiter):
    """Con ventana corta, tras esperar, se puede volver a consumir."""
    for _ in range(2):
        await limiter.check_and_record("k", limit=2, window_seconds=0.2)

    ok, _ = await limiter.check_and_record("k", limit=2, window_seconds=0.2)
    assert ok is False

    # Esperar a que expire la ventana
    await asyncio.sleep(0.25)
    ok, _ = await limiter.check_and_record("k", limit=2, window_seconds=0.2)
    assert ok is True


@pytest.mark.asyncio
async def test_different_keys_independent(limiter):
    for _ in range(3):
        await limiter.check_and_record("a", limit=3, window_seconds=60)
    # a está al límite
    ok, _ = await limiter.check_and_record("a", limit=3, window_seconds=60)
    assert ok is False
    # b está limpio
    ok, _ = await limiter.check_and_record("b", limit=3, window_seconds=60)
    assert ok is True


@pytest.mark.asyncio
async def test_limit_zero_disables(limiter):
    for _ in range(100):
        ok, _ = await limiter.check_and_record("k", limit=0, window_seconds=60)
        assert ok is True


@pytest.mark.asyncio
async def test_reset_clears_key(limiter):
    for _ in range(3):
        await limiter.check_and_record("k", limit=3, window_seconds=60)
    ok, _ = await limiter.check_and_record("k", limit=3, window_seconds=60)
    assert ok is False

    limiter.reset("k")
    ok, _ = await limiter.check_and_record("k", limit=3, window_seconds=60)
    assert ok is True


@pytest.mark.asyncio
async def test_get_limiter_is_singleton():
    a = get_limiter()
    b = get_limiter()
    assert a is b


@pytest.mark.asyncio
async def test_concurrent_hits_respect_limit(limiter):
    """Con concurrencia, no debe excederse el límite."""
    async def hit():
        return await limiter.check_and_record("k", limit=5, window_seconds=60)

    results = await asyncio.gather(*[hit() for _ in range(20)])
    allowed = sum(1 for ok, _ in results if ok)
    assert allowed == 5