from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.utils.notifier import AdminNotifier


@pytest.fixture
def bot():
    b = MagicMock(db_pool=MagicMock())
    b.cache = None
    return b


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


def _setup_channel(bot, config=None):
    if config is None:
        config = {"notify_channel_id": 123}
    bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config(config))
    channel = AsyncMock(spec=discord.TextChannel)
    bot.get_channel.return_value = channel
    return channel


class TestGetNotifyChannelId:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "config,expected",
        [
            ({"notify_channel_id": 123}, 123),
            ({"notify_channel_id": "456"}, 456),
            (None, None),
            ({}, None),
            ({"other": "val"}, None),
        ],
    )
    async def test_cases(self, notifier, bot, config, expected):
        conn = _conn_with_config(config)
        bot.db_pool.acquire.return_value = _db_ctx(conn)
        result = await notifier.get_notify_channel_id(999)
        assert result == expected

    @pytest.mark.asyncio
    async def test_cache_hit_returns_value(self, notifier, bot):
        bot.cache = MagicMock()
        bot.cache.get.return_value = 456
        result = await notifier.get_notify_channel_id(999)
        assert result == 456
        bot.db_pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_sentinel_returns_none(self, notifier, bot):
        bot.cache = MagicMock()
        bot.cache.get.return_value = -1
        result = await notifier.get_notify_channel_id(999)
        assert result is None
        bot.db_pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_sets_cache(self, notifier, bot):
        bot.cache = MagicMock()
        bot.cache.get.return_value = None
        conn = _conn_with_config({"notify_channel_id": 789})
        bot.db_pool.acquire.return_value = _db_ctx(conn)
        result = await notifier.get_notify_channel_id(999)
        assert result == 789
        bot.cache.set.assert_called_once_with("notify_channel:999", 789, ttl=300)

    @pytest.mark.asyncio
    async def test_cache_miss_none_sets_sentinel(self, notifier, bot):
        bot.cache = MagicMock()
        bot.cache.get.return_value = None
        conn = _conn_with_config(None)
        bot.db_pool.acquire.return_value = _db_ctx(conn)
        result = await notifier.get_notify_channel_id(999)
        assert result is None
        bot.cache.set.assert_called_once_with("notify_channel:999", -1, ttl=300)


class TestGetNotifyChannel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "config,channel_exists,expected",
        [
            ({"notify_channel_id": 123}, True, True),
            (None, True, None),
            ({}, True, None),
            ({"other": "val"}, True, None),
            ({"notify_channel_id": 123}, False, None),
        ],
    )
    async def test_cases(self, notifier, bot, config, channel_exists, expected):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config(config))
        bot.get_channel.return_value = (
            MagicMock(spec=discord.TextChannel) if channel_exists and config else None
        )
        if config and not channel_exists and config.get("notify_channel_id"):
            bot.fetch_channel = AsyncMock(side_effect=Exception())
        result = await notifier.get_notify_channel(999)
        assert (result is not None) == (expected is True)

    @pytest.mark.asyncio
    async def test_fetch_channel_fallback_when_get_channel_misses(self, notifier, bot):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config({"notify_channel_id": 123}))
        bot.get_channel.return_value = None
        fetched = MagicMock(spec=discord.TextChannel)
        bot.fetch_channel = AsyncMock(return_value=fetched)
        result = await notifier.get_notify_channel(999)
        assert result is fetched
        bot.fetch_channel.assert_awaited_once_with(123)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("config", [[], "{}", 1])
    async def test_config_non_dict_returns_none(self, notifier, bot, config):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config(config))
        result = await notifier.get_notify_channel(999)
        assert result is None


class TestSetNotifyChannel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "channel_id,error,expected",
        [
            (123, False, True),
            (None, False, True),
            (123, True, False),
        ],
    )
    async def test_cases(self, notifier, bot, channel_id, error, expected):
        conn = AsyncMock()
        if error:
            conn.execute = AsyncMock(side_effect=Exception())
        bot.db_pool.acquire.return_value = _db_ctx(conn)
        assert await notifier.set_notify_channel(999, channel_id) is expected

    @pytest.mark.asyncio
    async def test_invalidates_cache(self, notifier, bot):
        conn = AsyncMock()
        bot.db_pool.acquire.return_value = _db_ctx(conn)
        bot.cache = MagicMock()
        assert await notifier.set_notify_channel(999, 123) is True
        bot.cache.delete.assert_called_once_with("notify_channel:999")


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


class TestGiveawayNotifications:
    @pytest.mark.asyncio
    async def test_created(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_giveaway_created(999, "Prize", 111, 222, datetime.now(timezone.utc))
        assert channel.send.call_args[1]["embed"].title == "Giveaway Created"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "winners,expected_text",
        [
            ([111], "<@111>"),
            ([], "No valid"),
        ],
    )
    async def test_ended(self, notifier, bot, winners, expected_text):
        channel = _setup_channel(bot)
        await notifier.notify_giveaway_ended(999, "Prize", winners, 10)
        fields = str([f.value for f in channel.send.call_args[1]["embed"].fields])
        assert expected_text in fields


class TestErrorNotifications:
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


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_get_notify_channel_non_integer_channel_id(self, notifier, bot):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config({"notify_channel_id": "abc"}))
        with pytest.raises((ValueError, TypeError)):
            await notifier.get_notify_channel(999)

    @pytest.mark.asyncio
    async def test_get_notify_channel_channel_id_zero(self, notifier, bot):
        bot.db_pool.acquire.return_value = _db_ctx(_conn_with_config({"notify_channel_id": 0}))
        bot.get_channel.return_value = None
        result = await notifier.get_notify_channel(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_notify_error_very_long_exception(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_error(999, ValueError("x" * 5000), "ctx")
        tb = next(f for f in channel.send.call_args[1]["embed"].fields if f.name == "Traceback")
        assert len(tb.value) <= 1032


class TestQuotebookNotifications:
    @pytest.mark.asyncio
    async def test_notify_quotebook_submitted(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_quotebook_submitted(999, "A quote", 111, "abc12345")
        embed = channel.send.call_args[1]["embed"]
        assert embed.title == "Quote Submitted"
        assert "A quote" in embed.description
        assert "approve" in embed.footer.text


class TestPermissionNotifications:
    @pytest.mark.asyncio
    async def test_notify_permission_changed_with_target_and_role(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_permission_changed(
            999, "Set role", "admin", target_id=111, changed_by_id=222, discord_role=333
        )
        fields = str(channel.send.call_args[1]["embed"].fields)
        assert "<@111>" in fields and "<@222>" in fields and "<@&333>" in fields

    @pytest.mark.asyncio
    async def test_notify_permission_changed_set_role_cleared(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_permission_changed(
            999, "Set role", "admin", target_id=None, changed_by_id=222, discord_role=None
        )
        fields = str(channel.send.call_args[1]["embed"].fields)
        assert "Cleared" in fields

    @pytest.mark.asyncio
    async def test_notify_permission_changed_no_role_field(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_permission_changed(
            999, "Removed", "admin", target_id=111, changed_by_id=222, discord_role=None
        )
        fields = str(channel.send.call_args[1]["embed"].fields)
        assert "<@111>" in fields and "<@222>" in fields
        assert "Cleared" not in fields and "<@&" not in fields


class TestReactionRoleNotifications:
    @pytest.mark.asyncio
    async def test_notify_reaction_role_setup(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_reaction_role_setup(999, "Added", "👍", 111, 222, 333, 444)
        embed = channel.send.call_args[1]["embed"]
        assert embed.title == "Reaction Role"
        assert "👍" in embed.description and "Jump" in str(embed.fields)


class TestFaqNotifications:
    @pytest.mark.asyncio
    async def test_notify_faq_changed(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_faq_changed(999, "Added", "rules", 111)
        embed = channel.send.call_args[1]["embed"]
        assert embed.title == "FAQ Changed"
        assert "Added" in embed.description and "rules" in embed.description


class TestNotifyChannelNotifications:
    @pytest.mark.asyncio
    async def test_notify_notify_channel_changed_with_channel(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_notify_channel_changed(999, 123, 111)
        assert "123" in channel.send.call_args[1]["embed"].description

    @pytest.mark.asyncio
    async def test_notify_notify_channel_changed_disabled(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_notify_channel_changed(999, None, 111)
        assert "disabled" in channel.send.call_args[1]["embed"].description.lower()


class TestRateLimitNotifications:
    @pytest.mark.asyncio
    async def test_notify_rate_limit_hit(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_rate_limit_hit(999, 111, "Slow down", "test_cmd")
        embed = channel.send.call_args[1]["embed"]
        assert embed.title == "Rate Limit Hit"
        assert "Slow down" in embed.description


class TestBotAddedNotifications:
    @pytest.mark.asyncio
    async def test_notify_bot_added(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_bot_added(999, "New Server", 50)
        embed = channel.send.call_args[1]["embed"]
        assert embed.title == "Bot Added to Server"
        assert "New Server" in embed.description
        assert "50" in str(embed.fields)


class TestModerationNotifications:
    @pytest.mark.asyncio
    async def test_notify_moderation_with_all_fields(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_moderation(
            999, "Kicked", 111, moderator_id=222, reason="Spam", extra="3 strikes"
        )
        fields = str(channel.send.call_args[1]["embed"].fields)
        assert "<@111>" in fields and "<@222>" in fields
        assert "Spam" in fields and "3 strikes" in fields

    @pytest.mark.asyncio
    async def test_notify_moderation_minimal(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_moderation(
            999, "Banned", 111, moderator_id=None, reason=None, extra=None
        )
        embed = channel.send.call_args[1]["embed"]
        assert embed.title == "Moderation"
        assert len(embed.fields) == 1
        assert embed.fields[0].name == "Target"


class TestFaqSubmissionNotifications:
    @pytest.mark.asyncio
    async def test_notify_faq_submission(self, notifier, bot):
        channel = _setup_channel(bot)
        await notifier.notify_faq_submission(999, "How do I X?", 111, "sub-123")
        embed = channel.send.call_args[1]["embed"]
        assert embed.title == "FAQ Question Submitted"
        assert "How do I X?" in embed.description
        assert "add" in embed.footer.text.lower()
