import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.whitelist_channel import get_whitelist_channel_id, set_whitelist_channel


@pytest.fixture
def pool_factory():
    def _make_pool(conn):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=None)
        pool = MagicMock()
        pool.acquire.return_value = ctx
        return pool

    return _make_pool


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_success(pool_factory):
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"whitelist_channel_id": 999}}
    pool = pool_factory(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result == 999


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_no_row(pool_factory):
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = pool_factory(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_empty_config(pool_factory):
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": None}
    pool = pool_factory(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_config_not_dict(pool_factory):
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": "not a dict"}
    pool = pool_factory(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_no_channel_key(pool_factory):
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"other_key": 1}}
    pool = pool_factory(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_exception_returns_none(caplog, pool_factory):
    caplog.set_level(logging.WARNING, logger="bot.utils.server_config")
    conn = AsyncMock()
    conn.fetchrow.side_effect = Exception("DB error")
    pool = pool_factory(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None
    assert "Failed to get servers config" in caplog.text


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_cache_hit_returns_value(pool_factory):
    pool = pool_factory(AsyncMock())
    cache = MagicMock()
    cache.get.return_value = {"whitelist_channel_id": 777}
    result = await get_whitelist_channel_id(pool, 123, cache=cache)
    # Ensure the value comes from the cached object's 'whitelist_channel_id' key
    assert cache.get.return_value == {"whitelist_channel_id": 777}
    assert result == cache.get.return_value["whitelist_channel_id"]
    cache.get.assert_called_once_with("servers_config:123")
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_cache_hit_empty_returns_none():
    pool = make_pool(AsyncMock())
    cache = MagicMock()
    cache.get.return_value = {}
    result = await get_whitelist_channel_id(pool, 123, cache=cache)
    assert result is None
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_cache_miss_sets_cache():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"whitelist_channel_id": 888}}
    pool = make_pool(conn)
    cache = MagicMock()
    cache.get.return_value = None
    result = await get_whitelist_channel_id(pool, 123, cache=cache)
    assert result == 888
    cache.set.assert_called_once_with(
        "servers_config:123", {"whitelist_channel_id": 888}, ttl=86400
    )


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_cache_miss_none_sets_empty():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = make_pool(conn)
    cache = MagicMock()
    cache.get.return_value = None
    result = await get_whitelist_channel_id(pool, 123, cache=cache)
    assert result is None
    cache.set.assert_called_once_with("servers_config:123", {}, ttl=86400)


@pytest.mark.asyncio
async def test_set_whitelist_channel_with_id():
    conn = AsyncMock()
    pool = make_pool(conn)

    result = await set_whitelist_channel(pool, 123, 999)
    assert result is True
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    assert 123 in call_args[0]
    assert {"whitelist_channel_id": 999} in call_args[0]


@pytest.mark.asyncio
async def test_set_whitelist_channel_clear():
    conn = AsyncMock()
    pool = make_pool(conn)

    result = await set_whitelist_channel(pool, 123, None)
    assert result is True
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    assert call_args.args[1] == "whitelist_channel_id"
    assert call_args.args[2] == 123


@pytest.mark.asyncio
async def test_set_whitelist_channel_exception_returns_false(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.channel_config")
    conn = AsyncMock()
    conn.execute.side_effect = Exception("DB error")
    pool = make_pool(conn)

    result = await set_whitelist_channel(pool, 123, 999)
    assert result is False
    assert "Failed to set" in caplog.text


@pytest.mark.asyncio
async def test_set_whitelist_channel_invalidates_cache():
    conn = AsyncMock()
    pool = make_pool(conn)
    cache = MagicMock()
    result = await set_whitelist_channel(pool, 123, 999, cache=cache)
    assert result is True
    cache.delete.assert_called_once_with("servers_config:123")
