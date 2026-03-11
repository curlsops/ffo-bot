import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.quotebook_channel import get_quotebook_channel_id, set_quotebook_channel


def make_pool(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_success():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"quotebook_channel_id": 999}}
    pool = make_pool(conn)

    result = await get_quotebook_channel_id(pool, 123)
    assert result == 999


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_no_row():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = make_pool(conn)

    result = await get_quotebook_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_empty_config():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": None}
    pool = make_pool(conn)

    result = await get_quotebook_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_config_not_dict():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": "not a dict"}
    pool = make_pool(conn)

    result = await get_quotebook_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_no_channel_key():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"other_key": 1}}
    pool = make_pool(conn)

    result = await get_quotebook_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_exception_returns_none(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.quotebook_channel")
    conn = AsyncMock()
    conn.fetchrow.side_effect = Exception("DB error")
    pool = make_pool(conn)

    result = await get_quotebook_channel_id(pool, 123)
    assert result is None
    assert "Failed to get quotebook channel" in caplog.text


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_cache_hit_returns_value():
    pool = make_pool(AsyncMock())
    cache = MagicMock()
    cache.get.return_value = 777
    result = await get_quotebook_channel_id(pool, 123, cache=cache)
    assert result == 777
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_cache_hit_sentinel_returns_none():
    pool = make_pool(AsyncMock())
    cache = MagicMock()
    cache.get.return_value = -1
    result = await get_quotebook_channel_id(pool, 123, cache=cache)
    assert result is None
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_cache_miss_sets_cache():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"quotebook_channel_id": 888}}
    pool = make_pool(conn)
    cache = MagicMock()
    cache.get.return_value = None
    result = await get_quotebook_channel_id(pool, 123, cache=cache)
    assert result == 888
    cache.set.assert_called_once_with("quotebook_channel:123", 888, ttl=86400)


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_cache_miss_none_sets_sentinel():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = make_pool(conn)
    cache = MagicMock()
    cache.get.return_value = None
    result = await get_quotebook_channel_id(pool, 123, cache=cache)
    assert result is None
    cache.set.assert_called_once_with("quotebook_channel:123", -1, ttl=86400)


@pytest.mark.asyncio
async def test_set_quotebook_channel_with_id():
    conn = AsyncMock()
    pool = make_pool(conn)

    result = await set_quotebook_channel(pool, 123, 999)
    assert result is True
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert 999 in call_args or "999" in str(call_args)


@pytest.mark.asyncio
async def test_set_quotebook_channel_clear():
    conn = AsyncMock()
    pool = make_pool(conn)

    result = await set_quotebook_channel(pool, 123, None)
    assert result is True
    conn.execute.assert_called_once()
    assert "quotebook_channel_id" in conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_set_quotebook_channel_exception_returns_false(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.quotebook_channel")
    conn = AsyncMock()
    conn.execute.side_effect = Exception("DB error")
    pool = make_pool(conn)

    result = await set_quotebook_channel(pool, 123, 999)
    assert result is False
    assert "Failed to set quotebook channel" in caplog.text


@pytest.mark.asyncio
async def test_set_quotebook_channel_invalidates_cache():
    conn = AsyncMock()
    pool = make_pool(conn)
    cache = MagicMock()
    result = await set_quotebook_channel(pool, 123, 999, cache=cache)
    assert result is True
    cache.delete.assert_called_once_with("quotebook_channel:123")
