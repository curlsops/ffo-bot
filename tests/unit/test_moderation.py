from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.moderation import ModerationHandler


@pytest.fixture
def bot():
    b = MagicMock()
    b.notifier = MagicMock()
    b.notifier.notify_moderation = AsyncMock()
    b.settings = MagicMock(feature_notify_moderation=True)
    return b


@pytest.fixture
def handler(bot):
    return ModerationHandler(bot)


def _member(guild_id=1, user_id=10, nick=None, name="User", global_name="User"):
    m = MagicMock()
    m.guild.id = guild_id
    m.id = user_id
    m.nick = nick
    m.name = name
    m.global_name = global_name
    m.communication_disabled_until = None
    return m


class TestModerationUsernameChange:
    @pytest.mark.asyncio
    async def test_notifies_on_username_change(self, handler, bot):
        before = _member(name="OldName", global_name="OldDisplay")
        after = _member(name="NewName", global_name="OldDisplay")
        await handler.on_member_update(before, after)
        bot.notifier.notify_moderation.assert_awaited_once()
        call = bot.notifier.notify_moderation.call_args
        assert call.args[1] == "Discord Username Changed"
        assert "OldName" in str(call.kwargs.get("extra", ""))
        assert "NewName" in str(call.kwargs.get("extra", ""))

    @pytest.mark.asyncio
    async def test_notifies_on_global_name_change(self, handler, bot):
        before = _member(name="Same", global_name="OldDisplay")
        after = _member(name="Same", global_name="NewDisplay")
        await handler.on_member_update(before, after)
        bot.notifier.notify_moderation.assert_awaited_once()
        assert "OldDisplay" in str(bot.notifier.notify_moderation.call_args.kwargs.get("extra", ""))


class TestModerationTimeout:
    @pytest.mark.asyncio
    async def test_notifies_on_timeout_added(self, handler, bot):
        before = _member()
        after = _member()
        after.communication_disabled_until = datetime(2025, 12, 31, 12, 0, tzinfo=timezone.utc)

        async def audit_iter():
            entry = MagicMock()
            entry.target = MagicMock()
            entry.target.id = before.id
            entry.user = MagicMock()
            entry.user.id = 99
            entry.reason = "Spam"
            yield entry

        before.guild.audit_logs = lambda **kw: audit_iter()
        await handler.on_member_update(before, after)
        bot.notifier.notify_moderation.assert_awaited_once()
        call = bot.notifier.notify_moderation.call_args
        assert "Member Timed Out" in call.args[1]


class TestModerationVoiceState:
    @pytest.mark.asyncio
    async def test_notifies_on_server_mute(self, handler, bot):
        member = _member()
        member.guild.audit_logs = lambda **kw: _empty_async_iter()
        before_vs = MagicMock()
        before_vs.channel = MagicMock(name="general")
        before_vs.server_mute = False
        before_vs.server_deaf = False
        after_vs = MagicMock()
        after_vs.channel = before_vs.channel
        after_vs.server_mute = True
        after_vs.server_deaf = False
        await handler.on_voice_state_update(member, before_vs, after_vs)
        bot.notifier.notify_moderation.assert_awaited_once()
        assert "Server Muted" in bot.notifier.notify_moderation.call_args.args[1]


async def _empty_async_iter():
    for _ in []:
        yield


class TestModerationMessageDelete:
    @pytest.mark.asyncio
    async def test_notifies_on_message_delete(self, handler, bot):
        msg = MagicMock()
        msg.guild.id = 1
        msg.channel.id = 2
        msg.author.id = 10
        msg.author.bot = False
        msg.content = "deleted text"
        msg.attachments = []
        msg.guild.audit_logs = lambda **kw: _empty_async_iter()
        await handler.on_message_delete(msg)
        bot.notifier.notify_moderation.assert_awaited_once()
        call = bot.notifier.notify_moderation.call_args
        assert "Message Deleted" in call.args[1]
        assert "deleted text" in str(call.kwargs.get("extra", ""))

    @pytest.mark.asyncio
    async def test_skips_bot_messages(self, handler, bot):
        msg = MagicMock()
        msg.guild.id = 1
        msg.author.bot = True
        await handler.on_message_delete(msg)
        bot.notifier.notify_moderation.assert_not_awaited()


class TestModerationBulkDelete:
    @pytest.mark.asyncio
    async def test_notifies_on_bulk_delete(self, handler, bot):
        channel = MagicMock()
        channel.guild.id = 1
        channel.id = 5
        channel.guild.audit_logs = lambda **kw: _empty_async_iter()
        messages = [MagicMock(), MagicMock(), MagicMock()]
        await handler.on_bulk_message_delete(messages, channel)
        bot.notifier.notify_moderation.assert_awaited_once()
        call = bot.notifier.notify_moderation.call_args
        assert "Bulk Message Delete" in call.args[1]
        assert "3" in str(call.kwargs.get("extra", ""))


class TestModerationShouldNotify:
    @pytest.mark.asyncio
    async def test_skips_when_feature_disabled(self, handler, bot):
        bot.settings.feature_notify_moderation = False
        before = _member()
        after = _member(name="NewName")
        await handler.on_member_update(before, after)
        bot.notifier.notify_moderation.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_no_notifier(self, handler, bot):
        bot.notifier = None
        before = _member()
        after = _member(name="NewName")
        await handler.on_member_update(before, after)
