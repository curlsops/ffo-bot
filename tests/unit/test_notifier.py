from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.utils.notifier import AdminNotifier


@pytest.fixture
def bot():
    return MagicMock(db_pool=MagicMock())


@pytest.fixture
def notifier(bot):
    return AdminNotifier(bot)


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _conn_with_config(config):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"config": config} if config is not None else None)
    return conn


def _setup_channel(bot, config={"notify_channel_id": 123}):
    bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config(config))
    channel = AsyncMock(spec=discord.TextChannel)
    bot.get_channel.return_value = channel
    return channel


class TestGetNotifyChannel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("config,channel_exists,expected", [
        ({"notify_channel_id": 123}, True, True),
        (None, True, None),
        ({}, True, None),
        ({"other": "val"}, True, None),
        ({"notify_channel_id": 123}, False, None),
    ])
    async def test_cases(self, notifier, bot, config, channel_exists, expected):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config(config))
        bot.get_channel.return_value = MagicMock(spec=discord.TextChannel) if channel_exists and config else None
        result = await notifier.get_notify_channel(999)
        assert (result is not None) == (expected is True)

    @pytest.mark.asyncio
    async def test_config_must_be_dict(self, notifier, bot):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config("{}"))
        with pytest.raises(AttributeError, match="'str' object has no attribute 'get'"):
            await notifier.get_notify_channel(999)


class TestSetNotifyChannel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel_id,error,expected", [
        (123, False, True),
        (None, False, True),
        (123, True, False),
    ])
    async def test_cases(self, notifier, bot, channel_id, error, expected):
        conn = AsyncMock()
        if error:
            conn.execute = AsyncMock(side_effect=Exception())
        bot.db_pool.acquire.return_value = _db_ctx(conn)
        assert await notifier.set_notify_channel(999, channel_id) is expected


class TestSend:
    @pytest.mark.asyncio
    async def test_success(self, notifier, bot):
        channel = _setup_channel(bot)
        assert await notifier.send(999, discord.Embed()) is True
        channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_channel(self, notifier, bot):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config(None))
        assert await notifier.send(999, discord.Embed()) is False

    @pytest.mark.asyncio
    async def test_error(self, notifier, bot):
        channel = _setup_channel(bot)
        channel.send = AsyncMock(side_effect=Exception())
        assert await notifier.send(999, discord.Embed()) is False


class TestNotifyGiveaway:
    @pytest.mark.asyncio
    async def test_created(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_giveaway_created(999, "Prize", 111, 222, datetime.now(timezone.utc))
        assert channel.send.call_args[1]["embed"].title == "Giveaway Created"

    @pytest.mark.asyncio
    async def test_ended_with_winners(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_giveaway_ended(999, "Prize", [111], 10)
        assert any("<@111>" in f.value for f in channel.send.call_args[1]["embed"].fields)

    @pytest.mark.asyncio
    async def test_ended_no_winners(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_giveaway_ended(999, "Prize", [], 0)
        assert any("No valid" in f.value for f in channel.send.call_args[1]["embed"].fields)


class TestNotifyError:
    @pytest.mark.asyncio
    async def test_basic(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_error(999, ValueError("test"), "ctx")
        assert channel.send.call_args[1]["embed"].title == "Error"

    @pytest.mark.asyncio
    async def test_with_user_and_channel(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_error(999, Exception("err"), "ctx", user_id=111, channel_id=222)
        fields = str(channel.send.call_args[1]["embed"].fields)
        assert "<@111>" in fields and "<#222>" in fields

    @pytest.mark.asyncio
    async def test_truncates_long_traceback(self, notifier, bot):
        channel = _setup_channel(bot)
        try:
            raise ValueError("x" * 2000)
        except ValueError as e:
            await notifier.notify_error(999, e, "ctx")
        tb = next(f for f in channel.send.call_args[1]["embed"].fields if f.name == "Traceback")
        assert len(tb.value) <= 1032


class TestNotifyErrorAllServers:
    @pytest.mark.asyncio
    async def test_notifies_all(self, notifier, bot):
        conn = AsyncMock(fetch=AsyncMock(return_value=[{"server_id": 1}, {"server_id": 2}]),
                         fetchrow=AsyncMock(return_value={"config": {"notify_channel_id": 123}}))
        bot.db_pool.acquire.return_value = _db_ctx(conn)
        bot.get_channel.return_value = AsyncMock(spec=discord.TextChannel)
        await notifier.notify_error_all_servers(Exception("err"), "ctx")
        assert bot.get_channel.return_value.send.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_db_error(self, notifier, bot):
        bot.db_pool.acquire.return_value = _db_ctx(AsyncMock(fetch=AsyncMock(side_effect=Exception())))
        await notifier.notify_error_all_servers(Exception("err"), "ctx")
