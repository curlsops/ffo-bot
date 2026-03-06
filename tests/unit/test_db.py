import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.db import TRANSIENT_DB_ERRORS, cached_or_fallback


@pytest.mark.asyncio
async def test_cached_or_fallback_fetch_success():
    cache = MagicMock()
    fetch_fn = AsyncMock(return_value=[{"id": 1}])
    result = await cached_or_fallback(
        cache, "key", fetch_fn, 60, lambda r: [dict(x) for x in r] if r else None
    )
    assert result == [{"id": 1}]
    cache.set.assert_called_once_with("key", [{"id": 1}], ttl=60)


@pytest.mark.asyncio
async def test_cached_or_fallback_transient_error_uses_cache():
    cache = MagicMock()
    cache.get.return_value = [{"cached": 1}]
    fetch_fn = AsyncMock(side_effect=asyncio.TimeoutError())
    result = await cached_or_fallback(
        cache, "key", fetch_fn, 60, lambda r: [dict(x) for x in r] if r else None
    )
    assert result == [{"cached": 1}]
    cache.get.assert_called_once_with("key")


@pytest.mark.asyncio
async def test_cached_or_fallback_transient_error_no_cache_raises():
    fetch_fn = AsyncMock(side_effect=asyncio.TimeoutError())
    with pytest.raises(asyncio.TimeoutError):
        await cached_or_fallback(
            cache=None, cache_key="k", fetch_fn=fetch_fn, ttl=60, to_cache=lambda r: r
        )


@pytest.mark.asyncio
async def test_cached_or_fallback_transient_error_cache_miss_raises():
    cache = MagicMock()
    cache.get.return_value = None
    fetch_fn = AsyncMock(side_effect=asyncio.TimeoutError())
    with pytest.raises(asyncio.TimeoutError):
        await cached_or_fallback(cache, "key", fetch_fn, 60, lambda r: r)


@pytest.mark.asyncio
async def test_cached_or_fallback_none_result_not_cached():
    cache = MagicMock()
    fetch_fn = AsyncMock(return_value=None)
    to_cache = lambda r: dict(r) if r else None
    result = await cached_or_fallback(cache, "key", fetch_fn, 60, to_cache)
    assert result is None
    cache.set.assert_not_called()
