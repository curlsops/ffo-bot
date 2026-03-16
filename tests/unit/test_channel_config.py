from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.channel_config import set_channel_config


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
