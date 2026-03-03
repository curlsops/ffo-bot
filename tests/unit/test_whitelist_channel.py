"""Tests for whitelist channel utilities."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.whitelist_channel import get_whitelist_channel_id, set_whitelist_channel


def make_pool(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_success():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"whitelist_channel_id": 999}}
    pool = make_pool(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result == 999


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_no_row():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = make_pool(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_empty_config():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": None}
    pool = make_pool(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_config_not_dict():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": "not a dict"}
    pool = make_pool(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_no_channel_key():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"config": {"other_key": 1}}
    pool = make_pool(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_exception_returns_none(caplog):
    conn = AsyncMock()
    conn.fetchrow.side_effect = Exception("DB error")
    pool = make_pool(conn)

    result = await get_whitelist_channel_id(pool, 123)
    assert result is None
    assert "Failed to get whitelist channel" in caplog.text


@pytest.mark.asyncio
async def test_set_whitelist_channel_with_id():
    conn = AsyncMock()
    pool = make_pool(conn)

    result = await set_whitelist_channel(pool, 123, 999)
    assert result is True
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert 999 in call_args or "999" in str(call_args)


@pytest.mark.asyncio
async def test_set_whitelist_channel_clear():
    conn = AsyncMock()
    pool = make_pool(conn)

    result = await set_whitelist_channel(pool, 123, None)
    assert result is True
    conn.execute.assert_called_once()
    assert "whitelist_channel_id" in conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_set_whitelist_channel_exception_returns_false(caplog):
    conn = AsyncMock()
    conn.execute.side_effect = Exception("DB error")
    pool = make_pool(conn)

    result = await set_whitelist_channel(pool, 123, 999)
    assert result is False
    assert "Failed to set whitelist channel" in caplog.text
