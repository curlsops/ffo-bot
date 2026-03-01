"""Tests for giveaway manager."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[])
        manager.bot.db_pool = make_db_ctx(conn)
        await manager.check_giveaways()
        conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_giveaways_with_expired(self, manager):
        giveaway = {
            "id": uuid.uuid4(),
            "channel_id": 123,
            "message_id": 456,
            "host_id": 789,
            "donor_id": None,
            "prize": "Test Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[giveaway])
        manager.bot.db_pool = make_db_ctx(conn)
        with patch.object(manager, "_end_giveaway", new_callable=AsyncMock) as m:
            await manager.check_giveaways()
            m.assert_called_once_with(giveaway)

    @pytest.mark.asyncio
    async def test_check_giveaways_error(self, manager, caplog):
        conn = MagicMock()
        conn.fetch = AsyncMock(side_effect=Exception("DB error"))
        manager.bot.db_pool = make_db_ctx(conn)
        await manager.check_giveaways()
        assert "Giveaway check error" in caplog.text


class TestSelectWinners:
    def test_select_winners_empty(self, manager):
        assert manager._select_winners([], 1) == []

    def test_select_winners_single(self, manager):
        entries = [{"user_id": 1, "entries": 1}]
        winners = manager._select_winners(entries, 1)
        assert winners == [1]

    def test_select_winners_multiple(self, manager):
        entries = [
            {"user_id": 1, "entries": 1},
            {"user_id": 2, "entries": 1},
            {"user_id": 3, "entries": 1},
        ]
        winners = manager._select_winners(entries, 2)
        assert len(winners) == 2
        assert len(set(winners)) == 2

    def test_select_winners_weighted(self, manager):
        entries = [{"user_id": 1, "entries": 100}]
        winners = manager._select_winners(entries, 1)
        assert winners == [1]

    def test_select_winners_deduplicates(self, manager):
        from unittest.mock import patch
        entries = [
            {"user_id": 1, "entries": 3},
            {"user_id": 2, "entries": 1},
        ]
        with patch("random.shuffle"):
            winners = manager._select_winners(entries, 2)
        assert len(winners) == 2
        assert set(winners) == {1, 2}

    def test_select_winners_more_than_entries(self, manager):
        entries = [{"user_id": 1, "entries": 1}]
        winners = manager._select_winners(entries, 5)
        assert winners == [1]


class TestBuildEndedEmbed:
    def test_build_ended_embed_with_winners(self, manager):
        giveaway = {
            "prize": "Test",
            "host_id": 1,
            "donor_id": 2,
            "ended_at": datetime.now(timezone.utc),
        }
        embed = manager._build_ended_embed(giveaway, [100, 200], 10)
        assert embed.title == "🎉 GIVEAWAY ENDED 🎉"
        assert "Test" in embed.description

    def test_build_ended_embed_no_winners(self, manager):
        giveaway = {
            "prize": "Test",
            "host_id": 1,
            "donor_id": None,
            "ended_at": datetime.now(timezone.utc),
        }
        embed = manager._build_ended_embed(giveaway, [], 0)
        assert "No valid entries" in str([f.value for f in embed.fields])


class TestEndGiveaway:
    @pytest.mark.asyncio
    async def test_end_giveaway_no_entries(self, manager):
        giveaway = {
            "id": uuid.uuid4(),
            "channel_id": 123,
            "message_id": 456,
            "host_id": 789,
            "donor_id": None,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        manager.bot.db_pool = make_db_ctx(conn)
        channel = MagicMock()
        msg = MagicMock()
        msg.edit = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=msg)
        channel.send = AsyncMock()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(giveaway)
        channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_end_giveaway_with_winners(self, manager):
        giveaway = {
            "id": uuid.uuid4(),
            "channel_id": 123,
            "message_id": 456,
            "host_id": 789,
            "donor_id": None,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.executemany = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"user_id": 100, "entries": 1}])
        manager.bot.db_pool = make_db_ctx(conn)
        channel = MagicMock()
        msg = MagicMock()
        msg.edit = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=msg)
        channel.send = AsyncMock()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(giveaway)
        assert "Congratulations" in str(channel.send.call_args)

    @pytest.mark.asyncio
    async def test_end_giveaway_notifies_admin(self, manager):
        giveaway = {
            "id": uuid.uuid4(),
            "server_id": 999,
            "channel_id": 123,
            "message_id": 456,
            "host_id": 789,
            "donor_id": None,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.executemany = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"user_id": 100, "entries": 1}])
        manager.bot.db_pool = make_db_ctx(conn)
        channel = MagicMock()
        msg = MagicMock()
        msg.edit = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=msg)
        channel.send = AsyncMock()
        manager.bot.get_channel.return_value = channel
        manager.bot.notifier = MagicMock()
        manager.bot.notifier.notify_giveaway_ended = AsyncMock()

        await manager._end_giveaway(giveaway)

        manager.bot.notifier.notify_giveaway_ended.assert_awaited_once_with(
            999, "Prize", [100], 1
        )

    @pytest.mark.asyncio
    async def test_end_giveaway_no_channel(self, manager):
        giveaway = {
            "id": uuid.uuid4(),
            "channel_id": 123,
            "message_id": 456,
            "host_id": 789,
            "donor_id": None,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        manager.bot.db_pool = make_db_ctx(conn)
        manager.bot.get_channel.return_value = None
        await manager._end_giveaway(giveaway)

    @pytest.mark.asyncio
    async def test_end_giveaway_message_not_found(self, manager):
        import discord
        giveaway = {
            "id": uuid.uuid4(),
            "channel_id": 123,
            "message_id": 456,
            "host_id": 789,
            "donor_id": None,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        manager.bot.db_pool = make_db_ctx(conn)
        channel = MagicMock()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        channel.send = AsyncMock()
        manager.bot.get_channel.return_value = channel
        await manager._end_giveaway(giveaway)
        channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_end_giveaway_error(self, manager, caplog):
        giveaway = {
            "id": uuid.uuid4(),
            "channel_id": 123,
            "message_id": 456,
            "host_id": 789,
            "donor_id": None,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = MagicMock()
        conn.execute = AsyncMock(side_effect=Exception("Error"))
        manager.bot.db_pool = make_db_ctx(conn)
        await manager._end_giveaway(giveaway)
        assert "End giveaway error" in caplog.text


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.tasks.giveaway_manager import setup
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
