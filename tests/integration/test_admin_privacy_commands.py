from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.admin import AdminCommands
from bot.commands.privacy import PrivacyCommands


def make_interaction(guild=True):
    i = MagicMock()
    i.guild_id = 111
    i.user.id = 222
    i.guild = MagicMock() if guild else None
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.followup.send = AsyncMock()
    return i


def make_admin_bot(admin=True, notifier_success=True):
    bot = MagicMock()
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=admin)
    bot._register_server = AsyncMock()
    bot.notifier = MagicMock()
    bot.notifier.set_notify_channel = AsyncMock(return_value=notifier_success)
    return bot


@asynccontextmanager
async def mock_db_pool():
    conn = MagicMock()
    conn.execute = AsyncMock()
    yield conn


class TestAdminPing:
    @pytest.mark.asyncio
    async def test_sends_latency(self):
        bot = MagicMock(latency=0.123)
        await AdminCommands(bot).ping.callback(AdminCommands(bot), make_interaction())

    @pytest.mark.asyncio
    async def test_ping_latency_zero(self):
        bot = MagicMock(latency=0)
        i = make_interaction()
        i.response.send_message = AsyncMock()
        await AdminCommands(bot).ping.callback(AdminCommands(bot), i)
        assert "0ms" in i.response.send_message.call_args[0][0]


class TestSetNotifyChannel:
    @pytest.mark.asyncio
    async def test_success(self):
        bot = make_admin_bot()
        i = make_interaction()
        channel = MagicMock(id=123, mention="#c")
        await AdminCommands(bot).set_notify_channel.callback(AdminCommands(bot), i, channel=channel)
        bot._register_server.assert_awaited_once_with(i.guild)
        bot.notifier.set_notify_channel.assert_awaited_once_with(111, 123)

    @pytest.mark.asyncio
    async def test_disable(self):
        bot = make_admin_bot()
        i = make_interaction()
        await AdminCommands(bot).set_notify_channel.callback(AdminCommands(bot), i, channel=None)
        bot._register_server.assert_awaited_once_with(i.guild)
        bot.notifier.set_notify_channel.assert_awaited_once_with(111, None)

    @pytest.mark.asyncio
    async def test_no_guild(self):
        bot = make_admin_bot()
        i = make_interaction(guild=False)
        await AdminCommands(bot).set_notify_channel.callback(AdminCommands(bot), i, channel=None)
        assert "Server only" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_failure(self):
        bot = make_admin_bot(notifier_success=False)
        i = make_interaction()
        await AdminCommands(bot).set_notify_channel.callback(AdminCommands(bot), i, channel=None)
        assert "Failed" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_not_admin(self):
        bot = make_admin_bot(admin=False)
        i = make_interaction()
        await AdminCommands(bot).set_notify_channel.callback(AdminCommands(bot), i, channel=None)
        assert "Admin required" in i.followup.send.call_args[0][0]


class TestCheckAdmin:
    @pytest.mark.asyncio
    async def test_success(self):
        bot = make_admin_bot()
        assert await AdminCommands(bot)._check_admin(make_interaction(), "cmd") is True

    @pytest.mark.asyncio
    async def test_failure(self):
        bot = make_admin_bot(admin=False)
        i = make_interaction()
        assert await AdminCommands(bot)._check_admin(i, "cmd") is False
        i.followup.send.assert_awaited()


class TestPrivacy:
    @pytest.mark.asyncio
    async def test_optout(self):
        bot = MagicMock()
        bot.db_pool.acquire = mock_db_pool
        i = make_interaction()
        await PrivacyCommands(bot).privacy_optout.callback(PrivacyCommands(bot), i)
        i.followup.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_optin(self):
        bot = MagicMock()
        bot.db_pool.acquire = mock_db_pool
        i = make_interaction()
        await PrivacyCommands(bot).privacy_optin.callback(PrivacyCommands(bot), i)
        i.followup.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_optout_db_error(self):
        @asynccontextmanager
        async def bad_pool():
            conn = MagicMock()
            conn.execute = AsyncMock(side_effect=Exception("DB"))
            yield conn

        bot = MagicMock()
        bot.db_pool.acquire = lambda: bad_pool()
        i = make_interaction()
        await PrivacyCommands(bot).privacy_optout.callback(PrivacyCommands(bot), i)
        assert "error" in str(i.followup.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_optin_db_error(self):
        @asynccontextmanager
        async def bad_pool():
            conn = MagicMock()
            conn.execute = AsyncMock(side_effect=Exception("DB"))
            yield conn

        bot = MagicMock()
        bot.db_pool.acquire = lambda: bad_pool()
        i = make_interaction()
        await PrivacyCommands(bot).privacy_optin.callback(PrivacyCommands(bot), i)
        assert "error" in str(i.followup.send.call_args).lower()
