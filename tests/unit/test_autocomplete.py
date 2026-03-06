from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from bot.utils.autocomplete import cached_autocomplete


@pytest.mark.asyncio
async def test_cached_autocomplete_no_guild_returns_empty():
    async def fetch(pool, guild_id):
        return []

    i = MagicMock(guild_id=None)
    result = await cached_autocomplete(i, "", "key:{server_id}", fetch, lambda r, c: [], 300)
    assert result == []


@pytest.mark.asyncio
async def test_cached_autocomplete_fetches_and_caches():
    bot = MagicMock()
    bot.cache = MagicMock(get=MagicMock(return_value=None), set=MagicMock())
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"topic": "a"}, {"topic": "b"}])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    bot.db_pool.acquire.return_value = ctx

    async def fetch(pool, guild_id):
        return await conn.fetch()

    def to_choices(rows, current):
        return [
            app_commands.Choice(name=r["topic"], value=r["topic"])
            for r in rows
            if not current or current in r["topic"]
        ]

    i = MagicMock(guild_id=123, client=bot)
    result = await cached_autocomplete(i, "", "key:{server_id}", fetch, to_choices, ttl=60)
    assert len(result) == 2
    bot.cache.set.assert_called_once()
    assert "123" in str(bot.cache.set.call_args[0][0])


@pytest.mark.asyncio
async def test_cached_autocomplete_uses_cache_hit():
    bot = MagicMock()
    cached = [{"topic": "cached"}]
    bot.cache = MagicMock(get=MagicMock(return_value=cached), set=MagicMock())

    async def fetch(pool, guild_id):
        raise AssertionError("should not fetch when cache hit")

    def to_choices(rows, current):
        return [app_commands.Choice(name=r["topic"], value=r["topic"]) for r in rows]

    i = MagicMock(guild_id=1, client=bot)
    result = await cached_autocomplete(i, "", "key:{server_id}", fetch, to_choices)
    assert len(result) == 1
    assert result[0].value == "cached"
    bot.cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_cached_autocomplete_exception_returns_empty():
    bot = MagicMock()
    bot.cache = None

    async def fetch(pool, guild_id):
        raise ValueError("db error")

    def to_choices(rows, current):
        return []

    i = MagicMock(guild_id=1, client=bot)
    result = await cached_autocomplete(
        i, "", "key:{server_id}", fetch, to_choices, log_prefix="Test"
    )
    assert result == []
