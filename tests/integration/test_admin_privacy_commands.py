from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.admin import AdminCommands
from bot.commands.privacy import PrivacyCommands


def _i(guild=True):
    i = MagicMock()
    i.guild_id = 111
    i.user.id = 222
    i.guild = MagicMock() if guild else None
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.followup.send = AsyncMock()
    return i


def _admin_bot(admin=True, notifier_success=True, current_notify_channel_id=None):
    bot = MagicMock()
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=admin)
    bot._register_server = AsyncMock()
    bot.notifier = MagicMock()
    bot.notifier.get_notify_channel_id = AsyncMock(return_value=current_notify_channel_id)
    bot.notifier.get_notify_channel = AsyncMock(return_value=MagicMock(send=AsyncMock()))
    bot.notifier.set_notify_channel = AsyncMock(return_value=notifier_success)
    bot.notifier.notify_notify_channel_changed = AsyncMock()
    return bot


@asynccontextmanager
async def _pool(execute_raises=None):
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=execute_raises)
    yield conn


def _notify(bot, i, channel=None):
    g = AdminCommands(bot).admin_group
    return g.notify_channel.callback(g, i, channel=channel)


class TestAdminPing:
    @pytest.mark.asyncio
    async def test_sends_latency(self):
        bot = MagicMock(latency=0.123)
        await AdminCommands(bot).ping.callback(AdminCommands(bot), _i())

    @pytest.mark.asyncio
    async def test_ping_latency_zero(self):
        bot = MagicMock(latency=0)
        i = _i()
        i.response.send_message = AsyncMock()
        await AdminCommands(bot).ping.callback(AdminCommands(bot), i)
        assert "0ms" in i.response.send_message.call_args[0][0]


class TestSetNotifyChannel:
    @pytest.mark.asyncio
    async def test_success(self):
        bot = _admin_bot()
        i = _i()
        await _notify(bot, i, channel=MagicMock(id=123, mention="#c"))
        bot._register_server.assert_awaited_once_with(i.guild)
        bot.notifier.set_notify_channel.assert_awaited_once_with(111, 123)

    @pytest.mark.asyncio
    async def test_disable(self):
        bot = _admin_bot(current_notify_channel_id=123)
        await _notify(bot, _i(), channel=None)
        bot.notifier.set_notify_channel.assert_awaited_once_with(111, None)

    @pytest.mark.asyncio
    async def test_no_guild(self):
        bot = _admin_bot()
        i = _i(guild=False)
        await _notify(bot, i, channel=None)
        assert "Server only" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_failure(self):
        bot = _admin_bot(notifier_success=False, current_notify_channel_id=123)
        i = _i()
        await _notify(bot, i, channel=None)
        assert "Failed" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_already_set_to_channel(self):
        bot = _admin_bot(current_notify_channel_id=123)
        i = _i()
        await _notify(bot, i, channel=MagicMock(id=123, mention="#c"))
        assert "already set" in i.followup.send.call_args[0][0].lower()
        bot.notifier.set_notify_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_disabled(self):
        bot = _admin_bot(current_notify_channel_id=None)
        i = _i()
        await _notify(bot, i, channel=None)
        assert "already disabled" in i.followup.send.call_args[0][0].lower()
        bot.notifier.set_notify_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_admin(self):
        i = _i()
        await _notify(_admin_bot(admin=False), i, channel=None)
        assert "Admin required" in i.followup.send.call_args[0][0]


class TestVersion:
    @pytest.mark.asyncio
    async def test_success(self):
        bot = _admin_bot()
        i = _i()
        with patch("bot.commands.admin.importlib.metadata.version", return_value="1.3.7"):
            cog = AdminCommands(bot)
            await cog.admin_group.version.callback(cog.admin_group, i)
        assert "1.3.7" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_not_admin(self):
        bot = _admin_bot(admin=False)
        i = _i()
        cog = AdminCommands(bot)
        await cog.admin_group.version.callback(cog.admin_group, i)
        assert "Admin required" in i.followup.send.call_args[0][0]


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_success(self):
        from bot.auth.command_helpers import require_admin

        assert await require_admin(_i(), "cmd", _admin_bot()) is True

    @pytest.mark.asyncio
    async def test_failure(self):
        from bot.auth.command_helpers import require_admin

        bot = _admin_bot(admin=False)
        i = _i()
        assert await require_admin(i, "cmd", bot) is False
        i.followup.send.assert_awaited()


class TestPrivacy:
    @pytest.mark.asyncio
    async def test_optout(self):
        bot = MagicMock()
        bot.db_pool.acquire = _pool
        i = _i()
        cog = PrivacyCommands(bot)
        await cog.privacy_group.optout.callback(cog.privacy_group, i)
        i.followup.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_optin(self):
        bot = MagicMock()
        bot.db_pool.acquire = _pool
        i = _i()
        cog = PrivacyCommands(bot)
        await cog.privacy_group.optin.callback(cog.privacy_group, i)
        i.followup.send.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cmd", ["optout", "optin"])
    async def test_db_error(self, cmd):
        bot = MagicMock()
        bot.db_pool.acquire = lambda: _pool(Exception("DB"))
        i = _i()
        cog = PrivacyCommands(bot)
        await getattr(cog.privacy_group, cmd).callback(cog.privacy_group, i)
        assert "error" in str(i.followup.send.call_args).lower()
