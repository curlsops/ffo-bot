from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.whitelist_cache import get_cached_usernames
from bot.utils.whitelist_channel import get_whitelist_channel_id


def _make_pool(fetchrow=None):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow or None)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_no_row():
    pool = _make_pool(None)
    result = await get_whitelist_channel_id(pool, 1)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_empty_config():
    pool = _make_pool({"config": {}})
    result = await get_whitelist_channel_id(pool, 1)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_with_channel():
    pool = _make_pool({"config": {"whitelist_channel_id": 999}})
    result = await get_whitelist_channel_id(pool, 1)
    assert result == 999


def _make_fetch_pool(fetch_result):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=fetch_result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_get_cached_usernames_empty_db_returns_empty():
    pool = _make_fetch_pool([])
    result = await get_cached_usernames(pool, 1, None)
    assert result == []
