from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.channel_config import (
    fetch_music_voice_channel_targets,
    get_music_voice_channel_id,
    set_channel_config,
    set_music_voice_channel,
)


def make_pool(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_set_channel_config_rejects_invalid_key():
    conn = MagicMock()
    pool = make_pool(conn)

    result = await set_channel_config(pool, 123, "invalid_key", 999)
    assert result is False
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_set_channel_config_accepts_music_voice_channel_id():
    conn = MagicMock()
    conn.execute = AsyncMock()
    pool = make_pool(conn)
    result = await set_channel_config(pool, 7, "music_voice_channel_id", 555)
    assert result is True
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_music_voice_channel_targets():
    conn = MagicMock()
    conn.fetch = AsyncMock(
        return_value=[
            {"server_id": 1, "config": {"music_voice_channel_id": 99}},
            {"server_id": 2, "config": {"music_voice_channel_id": "101"}},
            {"server_id": 3, "config": {"music_voice_channel_id": "x"}},
        ]
    )
    pool = make_pool(conn)
    got = await fetch_music_voice_channel_targets(pool)
    assert got == [(1, 99), (2, 101)]


@pytest.mark.asyncio
async def test_fetch_music_voice_channel_targets_skips_repair_without_music_key():
    conn = MagicMock()
    conn.fetch = AsyncMock(
        return_value=[
            {"server_id": 1, "config": ["{}", '{"x": 1}']},
        ]
    )
    pool = make_pool(conn)
    assert await fetch_music_voice_channel_targets(pool) == []


@pytest.mark.asyncio
async def test_fetch_music_voice_channel_targets_skips_non_positive_channel_id():
    conn = MagicMock()
    conn.fetch = AsyncMock(
        return_value=[
            {"server_id": 1, "config": {"music_voice_channel_id": 0}},
            {"server_id": 2, "config": {"music_voice_channel_id": -3}},
        ]
    )
    pool = make_pool(conn)
    assert await fetch_music_voice_channel_targets(pool) == []


@pytest.mark.asyncio
async def test_get_music_voice_channel_id():
    with patch("bot.utils.channel_config.get_channel_config", AsyncMock(return_value=42)) as m:
        pool = MagicMock()
        assert await get_music_voice_channel_id(pool, 5) == 42
        m.assert_awaited_once_with(pool, 5, "music_voice_channel_id", None)


@pytest.mark.asyncio
async def test_set_music_voice_channel():
    with patch("bot.utils.channel_config.set_channel_config", AsyncMock(return_value=True)) as m:
        pool = MagicMock()
        assert await set_music_voice_channel(pool, 5, 99) is True
        m.assert_awaited_once_with(pool, 5, "music_voice_channel_id", 99, None)


@pytest.mark.asyncio
async def test_fetch_music_voice_channel_targets_db_error():
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    assert await fetch_music_voice_channel_targets(pool) == []
