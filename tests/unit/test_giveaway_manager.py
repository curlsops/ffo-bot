import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import discord
import pytest


def _giveaway(**overrides):
    return {
        "id": uuid.uuid4(),
        "server_id": 999,
        "channel_id": 123,
        "message_id": 456,
        "host_id": 789,
        "donor_id": None,
        "prize": "Prize",
        "winners_count": 1,
        "ended_at": datetime.now(timezone.utc),
        **overrides,
    }


def _channel_with_msg():
    msg = MagicMock(edit=AsyncMock())
    thread = MagicMock(add_user=AsyncMock(), send=AsyncMock())
    channel = MagicMock(
        fetch_message=AsyncMock(return_value=msg),
        send=AsyncMock(),
        create_thread=AsyncMock(return_value=thread),
    )
    return channel, msg


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


class ImmutableRecord:
    def __init__(self, data: dict):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def __setitem__(self, key, value):
        raise TypeError("'asyncpg.protocol.record.Record' object does not support item assignment")


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.settings = MagicMock(feature_giveaways=True)
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = MagicMock(return_value=None)
    bot.notifier = None
    return bot


@pytest.fixture
def manager(mock_bot):
    from bot.tasks.giveaway_manager import GiveawayManager

    return GiveawayManager(mock_bot)


class TestGiveawayManagerLifecycle:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("enabled,should_start", [(True, True), (False, False)])
    async def test_cog_load(self, manager, enabled, should_start):
        manager.bot.settings.feature_giveaways = enabled
        with patch.object(manager.check_giveaways, "start") as m:
            await manager.cog_load()
            assert m.called == should_start

    @pytest.mark.asyncio
    async def test_cog_unload(self, manager):
        with patch.object(manager.check_giveaways, "cancel") as m:
            await manager.cog_unload()
            m.assert_called_once()

    @pytest.mark.asyncio
    async def test_before_check(self, manager):
        await manager.before_check()
        manager.bot.wait_until_ready.assert_called_once()


class TestCheckGiveaways:
    @pytest.mark.asyncio
    async def test_no_expired(self, manager):
        manager.bot.db_pool = _db_ctx(MagicMock(fetch=AsyncMock(return_value=[])))
        await manager.check_giveaways()

    @pytest.mark.asyncio
    async def test_with_expired(self, manager):
        giveaway = _giveaway()
        manager.bot.db_pool = _db_ctx(MagicMock(fetch=AsyncMock(return_value=[giveaway])))
        with patch.object(manager, "_end_giveaway", new_callable=AsyncMock) as m:
            await manager.check_giveaways()
            m.assert_called_once_with(giveaway)

    @pytest.mark.asyncio
    async def test_error(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(MagicMock(fetch=AsyncMock(side_effect=Exception("DB error"))))
        await manager.check_giveaways()
        assert "Giveaway check error" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc",
        [
            asyncpg.CannotConnectNowError("pool closed"),
            asyncpg.ConnectionDoesNotExistError("connection lost"),
        ],
    )
    async def test_db_unavailable_logs_warning(self, manager, caplog, exc):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=exc)
        ctx.__aexit__ = AsyncMock(return_value=None)
        manager.bot.db_pool = MagicMock(acquire=MagicMock(return_value=ctx))
        await manager.check_giveaways()
        assert "Giveaway check skipped" in caplog.text
        assert "DB unavailable" in caplog.text


class TestSelectWinners:
    @pytest.mark.parametrize(
        "entries,winners_count,expected_len,expected_set",
        [
            ([], 1, 0, set()),
            ([{"user_id": 1, "entries": 1}], 1, 1, {1}),
            ([{"user_id": 1, "entries": 1}], 5, 1, {1}),
            ([{"user_id": 1, "entries": 100}], 1, 1, {1}),
        ],
    )
    def test_cases(self, manager, entries, winners_count, expected_len, expected_set):
        winners = manager._select_winners(entries, winners_count)
        assert len(winners) == expected_len
        if expected_set:
            assert set(winners) == expected_set

    def test_multiple(self, manager):
        entries = [{"user_id": i, "entries": 1} for i in range(3)]
        winners = manager._select_winners(entries, 2)
        assert len(winners) == 2 and len(set(winners)) == 2

    def test_deduplicates(self, manager):
        entries = [{"user_id": 1, "entries": 3}, {"user_id": 2, "entries": 1}]
        with patch("random.shuffle"):
            assert set(manager._select_winners(entries, 2)) == {1, 2}

    def test_zero_entries_user_never_wins(self, manager):
        entries = [{"user_id": 1, "entries": 0}, {"user_id": 2, "entries": 1}]
        for _ in range(10):
            assert manager._select_winners(entries, 1) == [2]

    def test_entries_equals_winners_count(self, manager):
        entries = [{"user_id": i, "entries": 1} for i in range(3)]
        winners = manager._select_winners(entries, 3)
        assert len(winners) == 3 and set(winners) == {0, 1, 2}

    def test_max_winners_50(self, manager):
        entries = [{"user_id": i, "entries": 1} for i in range(100)]
        winners = manager._select_winners(entries, 50)
        assert len(winners) == 50 and len(set(winners)) == 50


class TestBuildEndedEmbed:
    @pytest.mark.parametrize(
        "winners,entries,expected_text",
        [
            ([100, 200], 10, None),
            ([], 0, "No valid entries"),
        ],
    )
    def test_cases(self, manager, winners, entries, expected_text):
        embed = manager._build_ended_embed(_giveaway(prize="Test", donor_id=2), winners, entries)
        assert embed.title == "🎉 GIVEAWAY ENDED 🎉"
        if expected_text:
            assert expected_text in str([f.value for f in embed.fields])

    def test_includes_donor(self, manager):
        embed = manager._build_ended_embed(_giveaway(donor_id=555), [100], 5)
        assert "Donated by" in embed.description and "<@555>" in embed.description

    def test_winners_field(self, manager):
        embed = manager._build_ended_embed(_giveaway(), [10, 20], 3)
        assert "<@10>" in embed.fields[0].value and "<@20>" in embed.fields[0].value
        assert "2 winners" in embed.footer.text


class TestEndGiveaway:
    @pytest.mark.asyncio
    async def test_no_entries(self, manager):
        manager.bot.db_pool = _db_ctx(
            MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        )
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_with_winners(self, manager):
        manager.bot.db_pool = _db_ctx(
            MagicMock(
                execute=AsyncMock(),
                executemany=AsyncMock(),
                fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
            )
        )
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        assert "Congratulations" in str(channel.send.call_args)

    @pytest.mark.asyncio
    async def test_notifies_admin(self, manager):
        manager.bot.db_pool = _db_ctx(
            MagicMock(
                execute=AsyncMock(),
                executemany=AsyncMock(),
                fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
            )
        )
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock(notify_giveaway_ended=AsyncMock())
        await manager._end_giveaway(_giveaway())
        manager.bot.notifier.notify_giveaway_ended.assert_awaited_once_with(999, "Prize", [100], 1)

    @pytest.mark.asyncio
    async def test_notifier_exception_logged(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(
            MagicMock(
                execute=AsyncMock(),
                executemany=AsyncMock(),
                fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
            )
        )
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock(
            notify_giveaway_ended=AsyncMock(side_effect=Exception("notify"))
        )
        await manager._end_giveaway(_giveaway())
        assert "Notify giveaway ended failed" in caplog.text

    @pytest.mark.asyncio
    async def test_no_channel(self, manager):
        manager.bot.db_pool = _db_ctx(
            MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        )
        await manager._end_giveaway(_giveaway())

    @pytest.mark.asyncio
    async def test_fetch_channel_forbidden(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(
            MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        )
        manager.bot.get_channel.return_value = None
        manager.bot.fetch_channel = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        await manager._end_giveaway(_giveaway())
        assert "Could not fetch channel" in caplog.text

    @pytest.mark.asyncio
    async def test_fetch_channel_not_found(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(
            MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        )
        manager.bot.get_channel.return_value = None
        manager.bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        await manager._end_giveaway(_giveaway())
        assert "Could not fetch channel" in caplog.text

    @pytest.mark.asyncio
    async def test_message_not_found(self, manager):
        manager.bot.db_pool = _db_ctx(
            MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        )
        channel, _ = _channel_with_msg()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_error(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(MagicMock(execute=AsyncMock(side_effect=Exception("Error"))))
        await manager._end_giveaway(_giveaway())
        assert "End giveaway error" in caplog.text

    @pytest.mark.asyncio
    async def test_msg_edit_error_logged(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(
            MagicMock(
                execute=AsyncMock(),
                executemany=AsyncMock(),
                fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
            )
        )
        channel, msg = _channel_with_msg()
        msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        assert "End giveaway error" in caplog.text

    @pytest.mark.asyncio
    async def test_handles_asyncpg_record_immutability(self, manager):
        giveaway = ImmutableRecord(_giveaway())
        manager.bot.db_pool = _db_ctx(
            MagicMock(
                execute=AsyncMock(),
                executemany=AsyncMock(),
                fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
            )
        )
        channel, msg = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock(notify_giveaway_ended=AsyncMock())

        await manager._end_giveaway(giveaway)

        msg.edit.assert_called_once()
        assert "Congratulations" in str(channel.send.call_args)


class TestParseHostFromMessage:
    def test_extracts_host_from_mention(self):
        from bot.tasks.giveaway_manager import _parse_host_from_message

        msg = MagicMock(content="<@789> The giveaway has ended!")
        assert _parse_host_from_message(msg) == 789

    def test_extracts_host_from_nickname_mention(self):
        from bot.tasks.giveaway_manager import _parse_host_from_message

        msg = MagicMock(content="<@!789> The giveaway has ended!")
        assert _parse_host_from_message(msg) == 789

    def test_returns_none_for_empty_content(self):
        from bot.tasks.giveaway_manager import _parse_host_from_message

        msg = MagicMock(content="")
        assert _parse_host_from_message(msg) is None

    def test_returns_none_for_no_mentions(self):
        from bot.tasks.giveaway_manager import _parse_host_from_message

        msg = MagicMock(content="No mentions here")
        assert _parse_host_from_message(msg) is None


class TestCreatePrizeThread:
    @pytest.mark.asyncio
    async def test_creates_thread_and_adds_members(self, manager):
        channel, _ = _channel_with_msg()
        thread = channel.create_thread.return_value
        giveaway = _giveaway(host_id=789, prize="Cool Prize")
        winners = [100, 200]

        await manager._create_prize_thread(channel, giveaway, winners)

        channel.create_thread.assert_awaited_once_with(
            name="Cool Prize",
            message=None,
            invitable=False,
        )
        assert thread.add_user.await_count == 3  # host + 2 winners
        thread.send.assert_awaited_once()
        call_kw = thread.send.call_args[1]
        assert "<@789>" in call_kw["content"]
        assert "<@100>" in call_kw["content"]
        assert "<@200>" in call_kw["content"]
        embed = call_kw["embed"]
        assert "Giveaway Ended" in embed.title
        assert "Cool Prize" in embed.description
        assert "Congratulations" in embed.description
        assert call_kw["view"] is not None

    @pytest.mark.asyncio
    async def test_truncates_long_prize_name(self, manager):
        channel, _ = _channel_with_msg()
        long_prize = "A" * 100
        giveaway = _giveaway(prize=long_prize)
        await manager._create_prize_thread(channel, giveaway, [1])
        channel.create_thread.assert_awaited_once_with(
            name="A" * 80,
            message=None,
            invitable=False,
        )

    @pytest.mark.asyncio
    async def test_handles_add_user_failure(self, manager, caplog):
        channel, _ = _channel_with_msg()
        thread = channel.create_thread.return_value
        thread.add_user = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "nope"))
        await manager._create_prize_thread(channel, _giveaway(), [100])
        assert "Could not add user" in caplog.text
        thread.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_forbidden_create_thread(self, manager, caplog):
        channel, _ = _channel_with_msg()
        channel.create_thread = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        await manager._create_prize_thread(channel, _giveaway(), [100])
        assert "Cannot create prize thread" in caplog.text

    @pytest.mark.asyncio
    async def test_handles_generic_exception(self, manager, caplog):
        channel, _ = _channel_with_msg()
        channel.create_thread = AsyncMock(side_effect=Exception("boom"))
        await manager._create_prize_thread(channel, _giveaway(), [100])
        assert "Could not create prize thread" in caplog.text


class TestEndGiveawayPrizeThread:
    @pytest.mark.asyncio
    async def test_creates_prize_thread_when_winners(self, manager):
        manager.bot.db_pool = _db_ctx(
            MagicMock(
                execute=AsyncMock(),
                executemany=AsyncMock(),
                fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
            )
        )
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        channel.create_thread.assert_awaited_once()
        thread = channel.create_thread.return_value
        thread.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_prize_thread_when_no_winners(self, manager):
        manager.bot.db_pool = _db_ctx(
            MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        )
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        channel.create_thread.assert_not_called()


def _mock_thread(edit_side_effect=None):
    """Create a mock that passes isinstance(x, discord.Thread)."""
    thread = MagicMock(edit=AsyncMock(side_effect=edit_side_effect))
    thread.id = 12345
    # Make isinstance(thread, discord.Thread) True for the callback
    thread.__class__ = type("FakeThread", (discord.Thread,), {})
    return thread


class TestCloseGiveawayThreadView:
    def _interaction(
        self, *, is_admin=False, is_moderator=False, is_host=False, user_id=999, in_thread=True
    ):
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.user.id = 789 if is_host else user_id
        interaction.user.guild_permissions.administrator = is_admin
        interaction.channel = _mock_thread() if in_thread else MagicMock()
        interaction.client.permission_checker = MagicMock()
        interaction.client.permission_checker.check_role = AsyncMock(return_value=is_moderator)
        return interaction

    @pytest.fixture
    def view(self):
        from bot.tasks.giveaway_manager import CloseGiveawayThreadView

        return CloseGiveawayThreadView(host_id=789)

    @pytest.mark.asyncio
    async def test_host_can_close(self, view):
        interaction = self._interaction(is_host=True)

        await view._close_callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(locked=True, archived=True)
        call_kw = interaction.followup.send.call_args[1]
        assert call_kw["embed"].title == "🔒 Thread Closed"

    @pytest.mark.asyncio
    async def test_moderator_can_close(self, view):
        interaction = self._interaction(is_moderator=True)

        await view._close_callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(locked=True, archived=True)
        call_kw = interaction.followup.send.call_args[1]
        assert call_kw["embed"].title == "🔒 Thread Closed"

    @pytest.mark.asyncio
    async def test_admin_can_close(self, view):
        interaction = self._interaction(is_admin=True)

        await view._close_callback(interaction)

        interaction.channel.edit.assert_awaited_once_with(locked=True, archived=True)
        call_kw = interaction.followup.send.call_args[1]
        assert call_kw["embed"].title == "🔒 Thread Closed"

    @pytest.mark.asyncio
    async def test_unauthorized_denied(self, view):
        interaction = self._interaction()

        await view._close_callback(interaction)

        interaction.response.send_message.assert_awaited_with(
            "Only the host, server admins, or bot moderators can close this thread.",
            ephemeral=True,
        )

    @pytest.mark.asyncio
    async def test_not_in_thread_denied(self, view):
        interaction = self._interaction(in_thread=False)

        await view._close_callback(interaction)

        interaction.response.send_message.assert_awaited_with("Not in a thread.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_defer_not_found_returns_early(self, view):
        interaction = self._interaction(is_moderator=True)
        interaction.response.defer = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        await view._close_callback(interaction)

        interaction.followup.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_failure_sends_error(self, view):
        interaction = self._interaction(is_moderator=True)
        interaction.channel = _mock_thread(edit_side_effect=Exception("locked"))

        await view._close_callback(interaction)

        interaction.followup.send.assert_awaited_with("Failed to close thread.", ephemeral=True)


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.tasks.giveaway_manager import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
