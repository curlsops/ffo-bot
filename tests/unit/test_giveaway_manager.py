"""Tests for giveaway manager."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=msg)
    channel.send = AsyncMock()
    return channel, msg


class ImmutableRecord:
    """Simulates asyncpg.Record - supports item access but not assignment."""

    def __init__(self, data: dict):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def __setitem__(self, key, value):
        raise TypeError(
            "'asyncpg.protocol.record.Record' object does not support item assignment"
        )


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


def make_db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


class TestGiveawayManager:
    @pytest.mark.asyncio
    async def test_cog_load_enabled(self, manager):
        with patch.object(manager.check_giveaways, "start") as m:
            await manager.cog_load()
            m.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_load_disabled(self, manager):
        manager.bot.settings.feature_giveaways = False
        with patch.object(manager.check_giveaways, "start") as m:
            await manager.cog_load()
            m.assert_not_called()

    @pytest.mark.asyncio
    async def test_cog_unload(self, manager):
        with patch.object(manager.check_giveaways, "cancel") as m:
            await manager.cog_unload()
            m.assert_called_once()

    @pytest.mark.asyncio
    async def test_before_check(self, manager):
        await manager.before_check()
        manager.bot.wait_until_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_giveaways_no_expired(self, manager):
        conn = MagicMock(fetch=AsyncMock(return_value=[]))
        manager.bot.db_pool = make_db_ctx(conn)
        await manager.check_giveaways()
        conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_giveaways_with_expired(self, manager):
        giveaway = _giveaway(prize="Test Prize")
        conn = MagicMock(fetch=AsyncMock(return_value=[giveaway]))
        manager.bot.db_pool = make_db_ctx(conn)
        with patch.object(manager, "_end_giveaway", new_callable=AsyncMock) as m:
            await manager.check_giveaways()
            m.assert_called_once_with(giveaway)

    @pytest.mark.asyncio
    async def test_check_giveaways_error(self, manager, caplog):
        conn = MagicMock(fetch=AsyncMock(side_effect=Exception("DB error")))
        manager.bot.db_pool = make_db_ctx(conn)
        await manager.check_giveaways()
        assert "Giveaway check error" in caplog.text


class TestSelectWinners:
    def test_empty(self, manager):
        assert manager._select_winners([], 1) == []

    def test_single(self, manager):
        assert manager._select_winners([{"user_id": 1, "entries": 1}], 1) == [1]

    def test_multiple(self, manager):
        entries = [{"user_id": i, "entries": 1} for i in range(3)]
        winners = manager._select_winners(entries, 2)
        assert len(winners) == 2 and len(set(winners)) == 2

    def test_weighted(self, manager):
        assert manager._select_winners([{"user_id": 1, "entries": 100}], 1) == [1]

    def test_deduplicates(self, manager):
        entries = [{"user_id": 1, "entries": 3}, {"user_id": 2, "entries": 1}]
        with patch("random.shuffle"):
            winners = manager._select_winners(entries, 2)
        assert set(winners) == {1, 2}

    def test_more_than_entries(self, manager):
        assert manager._select_winners([{"user_id": 1, "entries": 1}], 5) == [1]


class TestBuildEndedEmbed:
    def test_with_winners(self, manager):
        embed = manager._build_ended_embed(_giveaway(prize="Test", donor_id=2), [100, 200], 10)
        assert embed.title == "🎉 GIVEAWAY ENDED 🎉" and "Test" in embed.description

    def test_no_winners(self, manager):
        embed = manager._build_ended_embed(_giveaway(), [], 0)
        assert "No valid entries" in str([f.value for f in embed.fields])


class TestEndGiveaway:
    @pytest.mark.asyncio
    async def test_no_entries(self, manager):
        conn = MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        manager.bot.db_pool = make_db_ctx(conn)
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_with_winners(self, manager):
        conn = MagicMock(
            execute=AsyncMock(),
            executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
        )
        manager.bot.db_pool = make_db_ctx(conn)
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        assert "Congratulations" in str(channel.send.call_args)

    @pytest.mark.asyncio
    async def test_notifies_admin(self, manager):
        conn = MagicMock(
            execute=AsyncMock(),
            executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
        )
        manager.bot.db_pool = make_db_ctx(conn)
        channel, _ = _channel_with_msg()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock(notify_giveaway_ended=AsyncMock())
        await manager._end_giveaway(_giveaway())
        manager.bot.notifier.notify_giveaway_ended.assert_awaited_once_with(999, "Prize", [100], 1)

    @pytest.mark.asyncio
    async def test_no_channel(self, manager):
        conn = MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        manager.bot.db_pool = make_db_ctx(conn)
        manager.bot.get_channel.return_value = None
        await manager._end_giveaway(_giveaway())

    @pytest.mark.asyncio
    async def test_message_not_found(self, manager):
        conn = MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        manager.bot.db_pool = make_db_ctx(conn)
        channel, _ = _channel_with_msg()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(_giveaway())
        channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_error(self, manager, caplog):
        conn = MagicMock(execute=AsyncMock(side_effect=Exception("Error")))
        manager.bot.db_pool = make_db_ctx(conn)
        await manager._end_giveaway(_giveaway())
        assert "End giveaway error" in caplog.text

    @pytest.mark.asyncio
    async def test_handles_asyncpg_record_immutability(self, manager):
        giveaway = ImmutableRecord(_giveaway())
        conn = MagicMock(
            execute=AsyncMock(),
            executemany=AsyncMock(),
            fetch=AsyncMock(return_value=[{"user_id": 100, "entries": 1}]),
        )
        manager.bot.db_pool = make_db_ctx(conn)
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
