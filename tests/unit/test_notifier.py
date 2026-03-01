from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.utils.notifier import AdminNotifier


@pytest.fixture
def bot():
    b = MagicMock()
    b.db_pool = MagicMock()
    return b


@pytest.fixture
def notifier(bot):
    return AdminNotifier(bot)


def db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def conn_with_config(config):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"config": config} if config is not None else None)
    return conn


class TestGetNotifyChannel:
    @pytest.mark.asyncio
    async def test_returns_channel(self, notifier, bot):
        conn = conn_with_config({"notify_channel_id": 123})
        bot.db_pool.acquire.return_value = db_ctx(conn)
        channel = MagicMock(spec=discord.TextChannel)
        bot.get_channel.return_value = channel
        assert await notifier.get_notify_channel(999) == channel

    @pytest.mark.asyncio
    async def test_no_row(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config(None))
        assert await notifier.get_notify_channel(999) is None

    @pytest.mark.asyncio
    async def test_empty_config(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({}))
        assert await notifier.get_notify_channel(999) is None

    @pytest.mark.asyncio
    async def test_no_channel_id_key(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"other": "val"}))
        assert await notifier.get_notify_channel(999) is None

    @pytest.mark.asyncio
    async def test_channel_not_found(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        bot.get_channel.return_value = None
        assert await notifier.get_notify_channel(999) is None


class TestSetNotifyChannel:
    @pytest.mark.asyncio
    async def test_set(self, notifier, bot):
        conn = AsyncMock()
        bot.db_pool.acquire.return_value = db_ctx(conn)
        assert await notifier.set_notify_channel(999, 123) is True

    @pytest.mark.asyncio
    async def test_remove(self, notifier, bot):
        conn = AsyncMock()
        bot.db_pool.acquire.return_value = db_ctx(conn)
        assert await notifier.set_notify_channel(999, None) is True

    @pytest.mark.asyncio
    async def test_error(self, notifier, bot):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=Exception())
        bot.db_pool.acquire.return_value = db_ctx(conn)
        assert await notifier.set_notify_channel(999, 123) is False


class TestSend:
    @pytest.mark.asyncio
    async def test_success(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        channel = AsyncMock(spec=discord.TextChannel)
        bot.get_channel.return_value = channel
        assert await notifier.send(999, discord.Embed()) is True
        channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_channel(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config(None))
        assert await notifier.send(999, discord.Embed()) is False

    @pytest.mark.asyncio
    async def test_error(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        channel = AsyncMock(spec=discord.TextChannel)
        channel.send = AsyncMock(side_effect=Exception())
        bot.get_channel.return_value = channel
        assert await notifier.send(999, discord.Embed()) is False


class TestNotifyGiveaway:
    @pytest.mark.asyncio
    async def test_created(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        channel = AsyncMock(spec=discord.TextChannel)
        bot.get_channel.return_value = channel
        await notifier.notify_giveaway_created(999, "Prize", 111, 222, datetime.now(timezone.utc))
        assert channel.send.call_args[1]["embed"].title == "Giveaway Created"

    @pytest.mark.asyncio
    async def test_ended_with_winners(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        channel = AsyncMock(spec=discord.TextChannel)
        bot.get_channel.return_value = channel
        await notifier.notify_giveaway_ended(999, "Prize", [111], 10)
        embed = channel.send.call_args[1]["embed"]
        assert any("<@111>" in f.value for f in embed.fields)

    @pytest.mark.asyncio
    async def test_ended_no_winners(self, notifier, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        channel = AsyncMock(spec=discord.TextChannel)
        bot.get_channel.return_value = channel
        await notifier.notify_giveaway_ended(999, "Prize", [], 0)
        embed = channel.send.call_args[1]["embed"]
        assert any("No valid entries" in f.value for f in embed.fields)
