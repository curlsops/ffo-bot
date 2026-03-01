import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import discord
import pytest


def _giveaway(**overrides):
    return {
        "id": uuid.uuid4(), "server_id": 999, "channel_id": 123, "message_id": 456,
        "host_id": 789, "donor_id": None, "prize": "Prize", "winners_count": 1,
        "ended_at": datetime.now(timezone.utc), **overrides,
    }


def _channel_with_msg():
    msg = MagicMock(edit=AsyncMock())
    channel = MagicMock(fetch_message=AsyncMock(return_value=msg), send=AsyncMock())
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
    @pytest.mark.parametrize("exc", [
        asyncpg.CannotConnectNowError("pool closed"),
        asyncpg.ConnectionDoesNotExistError("connection lost"),
    ])
    async def test_db_unavailable_logs_warning(self, manager, caplog, exc):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=exc)
        ctx.__aexit__ = AsyncMock(return_value=None)
        manager.bot.db_pool = MagicMock(acquire=MagicMock(return_value=ctx))
        await manager.check_giveaways()
        assert "Giveaway check skipped" in caplog.text
        assert "DB unavailable" in caplog.text


class TestSelectWinners:
    @pytest.mark.parametrize("entries,winners_count,expected_len,expected_set", [
        ([], 1, 0, set()),
        ([{"user_id": 1, "entries": 1}], 1, 1, {1}),
        ([{"user_id": 1, "entries": 1}], 5, 1, {1}),
        ([{"user_id": 1, "entries": 100}], 1, 1, {1}),
    ])
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
    @pytest.mark.parametrize("winners,entries,expected_text", [
        ([100, 200], 10, None),
        ([], 0, "No valid entries"),
    ])
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
        manager.bot.db_pool = _db_ctx(MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[])))
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_with_winners(self, manager):
        manager.bot.db_pool = _db_ctx(MagicMock(
            execute=AsyncMock(), executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}])
        ))
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        assert "Congratulations" in str(channel.send.call_args)

    @pytest.mark.asyncio
    async def test_notifies_admin(self, manager):
        manager.bot.db_pool = _db_ctx(MagicMock(
            execute=AsyncMock(), executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}])
        ))
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock(notify_giveaway_ended=AsyncMock())
        await manager._end_giveaway(_giveaway())
        manager.bot.notifier.notify_giveaway_ended.assert_awaited_once_with(999, "Prize", [100], 1)

    @pytest.mark.asyncio
    async def test_notifier_exception_logged(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(MagicMock(
            execute=AsyncMock(), executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}])
        ))
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock(notify_giveaway_ended=AsyncMock(side_effect=Exception("notify")))
        await manager._end_giveaway(_giveaway())
        assert "Notify giveaway ended failed" in caplog.text

    @pytest.mark.asyncio
    async def test_no_channel(self, manager):
        manager.bot.db_pool = _db_ctx(MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[])))
        await manager._end_giveaway(_giveaway())

    @pytest.mark.asyncio
    async def test_fetch_channel_forbidden(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[])))
        manager.bot.get_channel.return_value = None
        manager.bot.fetch_channel = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        await manager._end_giveaway(_giveaway())
        assert "Could not fetch channel" in caplog.text

    @pytest.mark.asyncio
    async def test_fetch_channel_not_found(self, manager, caplog):
        manager.bot.db_pool = _db_ctx(MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[])))
        manager.bot.get_channel.return_value = None
        manager.bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        await manager._end_giveaway(_giveaway())
        assert "Could not fetch channel" in caplog.text

    @pytest.mark.asyncio
    async def test_message_not_found(self, manager):
        manager.bot.db_pool = _db_ctx(MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[])))
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
        manager.bot.db_pool = _db_ctx(MagicMock(
            execute=AsyncMock(), executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}])
        ))
        channel, msg = _channel_with_msg()
        msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        assert "End giveaway error" in caplog.text

    @pytest.mark.asyncio
    async def test_handles_asyncpg_record_immutability(self, manager):
        giveaway = ImmutableRecord(_giveaway())
        manager.bot.db_pool = _db_ctx(MagicMock(
            execute=AsyncMock(), executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}])
        ))
        channel, msg = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock(notify_giveaway_ended=AsyncMock())

        await manager._end_giveaway(giveaway)

        msg.edit.assert_called_once()
        assert "Congratulations" in str(channel.send.call_args)


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.tasks.giveaway_manager import setup
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
