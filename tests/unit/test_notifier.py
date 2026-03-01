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
    def setup_channel(self, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        channel = AsyncMock(spec=discord.TextChannel)
        bot.get_channel.return_value = channel
        return channel

    @pytest.mark.asyncio
    async def test_created(self, notifier, bot):
        channel = self.setup_channel(bot)
        await notifier.notify_giveaway_created(999, "Prize", 111, 222, datetime.now(timezone.utc))
        assert channel.send.call_args[1]["embed"].title == "Giveaway Created"

    @pytest.mark.asyncio
    async def test_ended_with_winners(self, notifier, bot):
        channel = self.setup_channel(bot)
        await notifier.notify_giveaway_ended(999, "Prize", [111], 10)
        assert any("<@111>" in f.value for f in channel.send.call_args[1]["embed"].fields)

    @pytest.mark.asyncio
    async def test_ended_no_winners(self, notifier, bot):
        channel = self.setup_channel(bot)
        await notifier.notify_giveaway_ended(999, "Prize", [], 0)
        assert any("No valid" in f.value for f in channel.send.call_args[1]["embed"].fields)


class TestNotifyError:
    def setup_channel(self, bot):
        bot.db_pool.acquire.return_value = db_ctx(conn_with_config({"notify_channel_id": 123}))
        channel = AsyncMock(spec=discord.TextChannel)
        bot.get_channel.return_value = channel
        return channel

    @pytest.mark.asyncio
    async def test_basic(self, notifier, bot):
        channel = self.setup_channel(bot)
        await notifier.notify_error(999, ValueError("test"), "ctx")
        assert channel.send.call_args[1]["embed"].title == "Error"

    @pytest.mark.asyncio
    async def test_with_user_and_channel(self, notifier, bot):
        channel = self.setup_channel(bot)
        await notifier.notify_error(999, Exception("err"), "ctx", user_id=111, channel_id=222)
        fields = str(channel.send.call_args[1]["embed"].fields)
        assert "<@111>" in fields and "<#222>" in fields

    @pytest.mark.asyncio
    async def test_truncates_long_traceback(self, notifier, bot):
        channel = self.setup_channel(bot)
        try:
            raise ValueError("x" * 2000)
        except ValueError as e:
            await notifier.notify_error(999, e, "ctx")
        tb = next(f for f in channel.send.call_args[1]["embed"].fields if f.name == "Traceback")
        assert len(tb.value) <= 1032


class TestNotifyErrorAllServers:
    @pytest.mark.asyncio
    async def test_notifies_all(self, notifier, bot):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"server_id": 1}, {"server_id": 2}])
        conn.fetchrow = AsyncMock(return_value={"config": {"notify_channel_id": 123}})
        bot.db_pool.acquire.return_value = db_ctx(conn)
        bot.get_channel.return_value = AsyncMock(spec=discord.TextChannel)
        await notifier.notify_error_all_servers(Exception("err"), "ctx")
        assert bot.get_channel.return_value.send.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_db_error(self, notifier, bot):
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=Exception())
        bot.db_pool.acquire.return_value = db_ctx(conn)
        await notifier.notify_error_all_servers(Exception("err"), "ctx")
