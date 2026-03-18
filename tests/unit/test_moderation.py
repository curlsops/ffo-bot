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
    m.timed_out_until = None
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
        extra = call.kwargs.get("extra")
        assert isinstance(extra, str)
        assert "OldName" in extra
        assert "NewName" in extra

    @pytest.mark.asyncio
    async def test_notifies_on_global_name_change(self, handler, bot):
        before = _member(name="Same", global_name="OldDisplay")
        after = _member(name="Same", global_name="NewDisplay")
        await handler.on_member_update(before, after)
        bot.notifier.notify_moderation.assert_awaited_once()
        extra = bot.notifier.notify_moderation.call_args.kwargs.get("extra")
        assert isinstance(extra, str)
        assert "OldDisplay" in extra


class TestModerationTimeout:
    @pytest.mark.asyncio
    async def test_notifies_on_timeout_added(self, handler, bot):
        before = _member()
        after = _member()
        after.timed_out_until = datetime(2025, 12, 31, 12, 0, tzinfo=timezone.utc)

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

    @pytest.mark.asyncio
    async def test_reuses_member_update_audit_fetch_across_handlers(self, handler, bot):
        before = _member()
        after = _member()
        after.timed_out_until = datetime(2025, 12, 31, 12, 0, tzinfo=timezone.utc)

        call_count = 0

        async def audit_iter():
            entry = MagicMock()
            entry.target = MagicMock()
            entry.target.id = before.id
            entry.user = MagicMock()
            entry.user.id = 99
            entry.reason = "Spam"
            yield entry

        def audit_logs(**kw):
            nonlocal call_count
            call_count += 1
            return audit_iter()

        before.guild.audit_logs = audit_logs
        await handler._notify_timeout_change(before, after)

        channel = MagicMock()
        channel.name = "general"
        await handler._notify_voice_mod_action(before.guild, before.id, "Server Muted", channel)

        assert call_count == 1
        assert bot.notifier.notify_moderation.await_count == 2


async def _voice_audit_iter(target_id, moderator_id):
    entry = MagicMock()
    entry.target = MagicMock()
    entry.target.id = target_id
    entry.user = MagicMock()
    entry.user.id = moderator_id
    yield entry


class TestModerationVoiceState:
    @pytest.mark.asyncio
    async def test_notifies_on_server_mute_when_moderator_mutes_other(self, handler, bot):
        member = _member(user_id=10)
        member.guild.audit_logs = lambda **kw: _voice_audit_iter(10, 99)
        before_vs = MagicMock()
        before_vs.channel = MagicMock(name="general")
        before_vs.mute = False
        before_vs.deaf = False
        after_vs = MagicMock()
        after_vs.channel = before_vs.channel
        after_vs.mute = True
        after_vs.deaf = False
        await handler.on_voice_state_update(member, before_vs, after_vs)
        bot.notifier.notify_moderation.assert_awaited_once()
        assert "Server Muted" in bot.notifier.notify_moderation.call_args.args[1]

    @pytest.mark.asyncio
    async def test_skips_server_mute_when_self_mute(self, handler, bot):
        member = _member(user_id=10)
        member.guild.audit_logs = lambda **kw: _empty_async_iter()
        before_vs = MagicMock()
        before_vs.channel = MagicMock(name="general")
        before_vs.mute = False
        after_vs = MagicMock()
        after_vs.channel = before_vs.channel
        after_vs.mute = True
        after_vs.deaf = False
        await handler.on_voice_state_update(member, before_vs, after_vs)
        bot.notifier.notify_moderation.assert_not_awaited()


async def _empty_async_iter():
    for _ in []:
        yield


class TestModerationMessageDelete:
    @pytest.mark.asyncio
    async def test_notifies_on_message_delete_when_moderator_deletes(self, handler, bot):
        msg = MagicMock()
        msg.guild.id = 1
        msg.channel.id = 2
        msg.author.id = 10
        msg.author.bot = False
        msg.content = "deleted text"
        msg.attachments = []

        async def audit_iter():
            entry = MagicMock()
            entry.extra = MagicMock()
            entry.extra.channel = MagicMock()
            entry.extra.channel.id = 2
            entry.user = MagicMock()
            entry.user.id = 99
            yield entry

        msg.guild.audit_logs = lambda **kw: audit_iter()
        await handler.on_message_delete(msg)
        bot.notifier.notify_moderation.assert_awaited_once()
        call = bot.notifier.notify_moderation.call_args
        assert call.args[1] == "Message Deleted"
        extra = call.kwargs.get("extra")
        assert isinstance(extra, str)
        assert "deleted text" in extra

    @pytest.mark.asyncio
    async def test_skips_message_delete_when_self_delete(self, handler, bot):
        msg = MagicMock()
        msg.guild.id = 1
        msg.channel.id = 2
        msg.author.id = 10
        msg.author.bot = False
        msg.content = "deleted text"
        msg.attachments = []
        msg.guild.audit_logs = lambda **kw: _empty_async_iter()
        await handler.on_message_delete(msg)
        bot.notifier.notify_moderation.assert_not_awaited()

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
        extra = call.kwargs.get("extra")
        assert isinstance(extra, str)
        assert "Count: 3 messages" in extra


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
