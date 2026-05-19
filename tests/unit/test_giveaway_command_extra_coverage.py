from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from bot.commands import giveaway as giveaway_mod
from bot.commands.giveaway import (
    CACHE_GIVEAWAY_MESSAGE_ID,
    GIVEAWAY_DURATIONS,
    GiveawayCommands,
    _fetch_giveaway_message_ids,
    _giveaway_duration_autocomplete,
    _giveaway_message_id_autocomplete,
    _giveaway_message_ids_to_choices,
)
from tests.helpers import mock_db_pool
from tests.unit.giveaway_commands.conftest import OP_REROLL, OP_START, db_ctx, interaction


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.metrics.commands_executed.labels.return_value = MagicMock()
    return bot


@pytest.fixture
def cog(mock_bot):
    return GiveawayCommands(mock_bot)


class TestDurationAutocomplete:
    @pytest.mark.asyncio
    async def test_empty_current_returns_all_durations(self):
        i = MagicMock()
        out = await _giveaway_duration_autocomplete(i, "")
        assert len(out) == len(GIVEAWAY_DURATIONS)
        assert out[0].value in GIVEAWAY_DURATIONS

    @pytest.mark.asyncio
    async def test_filter_matches(self):
        i = MagicMock()
        out = await _giveaway_duration_autocomplete(i, "1h")
        assert out and all("1h" in c.value for c in out)

    @pytest.mark.asyncio
    async def test_no_match_falls_back(self):
        i = MagicMock()
        out = await _giveaway_duration_autocomplete(i, "zzzz")
        assert len(out) == len(GIVEAWAY_DURATIONS)


class TestMessageIdChoices:
    def test_long_prize_and_ended_label(self):
        long_prize = "x" * 50
        rows = [
            {
                "message_id": 99,
                "prize": long_prize,
                "ended_at": datetime.now(timezone.utc),
            }
        ]
        choices = _giveaway_message_ids_to_choices(rows, "")
        assert choices
        assert "ended" in choices[0].name
        assert len(choices[0].name) <= 100

    def test_filter_by_message_id(self):
        rows = [{"message_id": 123456789012345678, "prize": "A", "ended_at": None}]
        out = _giveaway_message_ids_to_choices(rows, "12345")
        assert out and out[0].value == "123456789012345678"

    def test_filter_by_prize_substring(self):
        rows = [{"message_id": 1, "prize": "UniquePrizeX", "ended_at": None}]
        out = _giveaway_message_ids_to_choices(rows, "unique")
        assert out

    def test_filter_excludes_non_matching_current(self):
        rows = [{"message_id": 111, "prize": "Alpha", "ended_at": None}]
        assert _giveaway_message_ids_to_choices(rows, "nomatchxyz") == []


@pytest.mark.asyncio
async def test_fetch_giveaway_message_ids():
    pool, conn = mock_db_pool(fetch=[{"message_id": 1, "prize": "p", "ended_at": None}])
    rows = await _fetch_giveaway_message_ids(pool, 9)
    conn.fetch.assert_awaited()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_message_id_autocomplete_wraps_cached(monkeypatch):
    calls = []

    async def fake_cached(interaction, current, cache_key, fetcher, mapper, **kw):
        calls.append((cache_key, fetcher, mapper))
        return [app_commands.Choice(name="x", value="1")]

    monkeypatch.setattr(giveaway_mod, "cached_autocomplete", fake_cached)
    i = MagicMock()
    out = await _giveaway_message_id_autocomplete(i, "")
    assert out and calls and CACHE_GIVEAWAY_MESSAGE_ID in calls[0][0]


@pytest.mark.asyncio
async def test_gstart_missing_required_fields(cog):
    i = interaction()
    await cog.giveaway_cmd.callback(
        i,
        operation=OP_START,
        duration=None,
        winners=1,
        prize="Prize",
    )
    assert "required" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_gstart_duration_below_minimum_after_parse(cog):
    cog.bot.db_pool = db_ctx(AsyncMock())
    i = interaction()
    await cog.giveaway_cmd.callback(
        i,
        operation=OP_START,
        duration="59s",
        winners=1,
        prize="Prize",
    )
    assert "Invalid duration" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_gstart_invalidates_message_cache(cog):
    cog.bot.cache = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cog.bot.db_pool = db_ctx(conn)
    i = interaction()
    await cog.giveaway_cmd.callback(
        i,
        operation=OP_START,
        duration="1h",
        winners=1,
        prize="Prize",
    )
    cog.bot.cache.delete.assert_called()


@pytest.mark.asyncio
async def test_gstart_metrics_notifier_and_no_cache_delete(cog):
    cog.bot.cache = None
    cog.bot.metrics = MagicMock()
    cog.bot.metrics.commands_executed.labels.return_value = MagicMock()
    cog.bot.notifier = MagicMock()
    cog.bot.notifier.notify_giveaway_created = AsyncMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cog.bot.db_pool = db_ctx(conn)
    i = interaction()
    await cog.giveaway_cmd.callback(
        i,
        operation=OP_START,
        duration="1h",
        winners=1,
        prize="Prize",
    )
    cog.bot.metrics.commands_executed.labels.return_value.inc.assert_called()
    cog.bot.notifier.notify_giveaway_created.assert_awaited_once()


@pytest.mark.asyncio
async def test_gstart_outer_exception(cog):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cog.bot.db_pool = db_ctx(conn)
    i = interaction()
    i.followup.send = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("bot.commands.giveaway.send_error", new_callable=AsyncMock) as se:
        await cog.giveaway_cmd.callback(
            i,
            operation=OP_START,
            duration="1h",
            winners=1,
            prize="Prize",
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_reroll_skips_executemany_when_no_final_winners(cog):
    current = {
        "id": 1,
        "is_active": False,
        "message_id": 123,
        "channel_id": 2,
        "prize": "Prize",
        "winners_count": 1,
        "ended_at": datetime.now(timezone.utc),
    }
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value=current),
        fetch=AsyncMock(
            side_effect=[
                [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                [{"user_id": 1}],
            ]
        ),
        execute=AsyncMock(),
        executemany=AsyncMock(),
    )
    cog.bot.db_pool = db_ctx(conn)
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=MagicMock(edit=AsyncMock()))
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)
    i = interaction()
    with patch.object(cog, "_select_winners", return_value=[]):
        with patch("bot.commands.giveaway.build_embed", return_value=discord.Embed()):
            with patch("bot.commands.giveaway.build_reroll_announcement", return_value="ann"):
                await cog.giveaway_cmd.callback(
                    i, operation=OP_REROLL, message_id="123456789012345678"
                )
    conn.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_reroll_message_fetch_not_found_still_completes(cog):
    current = {
        "id": 1,
        "is_active": False,
        "message_id": 123,
        "channel_id": 2,
        "prize": "Prize",
        "winners_count": 1,
        "ended_at": datetime.now(timezone.utc),
    }
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value=current),
        fetch=AsyncMock(
            side_effect=[
                [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                [{"user_id": 1}],
            ]
        ),
        execute=AsyncMock(),
        executemany=AsyncMock(),
    )
    cog.bot.db_pool = db_ctx(conn)
    channel = MagicMock()
    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)
    i = interaction()
    with patch.object(cog, "_select_winners", return_value=[2]):
        with patch("bot.commands.giveaway.build_embed", return_value=discord.Embed()):
            with patch("bot.commands.giveaway.build_reroll_announcement", return_value="ann"):
                await cog.giveaway_cmd.callback(
                    i, operation=OP_REROLL, message_id="123456789012345678"
                )
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_reroll_inner_exception_triggers_send_error(cog):
    current = {
        "id": 1,
        "is_active": False,
        "message_id": 123,
        "channel_id": 2,
        "prize": "Prize",
        "winners_count": 1,
        "ended_at": datetime.now(timezone.utc),
    }
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value=current),
        fetch=AsyncMock(
            side_effect=[
                [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                [{"user_id": 1}],
            ]
        ),
        execute=AsyncMock(),
        executemany=AsyncMock(),
    )
    cog.bot.db_pool = db_ctx(conn)
    msg = MagicMock(edit=AsyncMock())
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=msg)
    channel.send = AsyncMock(side_effect=RuntimeError("send failed"))
    cog.bot.get_channel = MagicMock(return_value=channel)
    i = interaction()
    with patch.object(cog, "_select_winners", return_value=[2]):
        with patch("bot.commands.giveaway.build_embed", return_value=discord.Embed()):
            with patch("bot.commands.giveaway.build_reroll_announcement", return_value="ann"):
                with patch("bot.commands.giveaway.send_error", new_callable=AsyncMock) as se:
                    await cog.giveaway_cmd.callback(
                        i, operation=OP_REROLL, message_id="123456789012345678"
                    )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_reroll_missing_message_id(cog):
    i = interaction()
    await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id=None)
    assert "Message ID required" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_reroll_count_zero(cog):
    current = {
        "id": 1,
        "is_active": False,
        "message_id": 123,
        "channel_id": 2,
        "prize": "Prize",
        "winners_count": 1,
        "ended_at": datetime.now(timezone.utc),
    }
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value=current),
        fetch=AsyncMock(
            side_effect=[
                [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                [{"user_id": 1}],
            ]
        ),
    )
    cog.bot.db_pool = db_ctx(conn)
    i = interaction()
    await cog.giveaway_cmd.callback(
        i,
        operation=OP_REROLL,
        message_id="123456789012345678",
        count=0,
    )
    assert "at least 1" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_reroll_updates_message_and_announces(cog):
    current = {
        "id": 1,
        "is_active": False,
        "message_id": 123,
        "channel_id": 2,
        "prize": "Prize",
        "winners_count": 1,
        "ended_at": datetime.now(timezone.utc),
    }
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value=current),
        fetch=AsyncMock(
            side_effect=[
                [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                [{"user_id": 1}],
            ]
        ),
        execute=AsyncMock(),
        executemany=AsyncMock(),
    )
    cog.bot.db_pool = db_ctx(conn)
    msg = MagicMock(edit=AsyncMock())
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=msg)
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)

    i = interaction()
    with patch.object(cog, "_select_winners", return_value=[2]):
        with patch("bot.commands.giveaway.build_embed", return_value=discord.Embed()):
            with patch("bot.commands.giveaway.build_reroll_announcement", return_value="ann"):
                await cog.giveaway_cmd.callback(
                    i, operation=OP_REROLL, message_id="123456789012345678"
                )
    msg.edit.assert_awaited()
    channel.send.assert_awaited()


@pytest.mark.asyncio
async def test_reroll_outer_exception(cog):
    cog.bot.db_pool = MagicMock(side_effect=RuntimeError("pool"))
    i = interaction()
    with patch("bot.commands.giveaway.send_error", new_callable=AsyncMock) as se:
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_giveaway_cog_load_unload():
    bot = MagicMock()
    bot.tree.add_command = MagicMock()
    cog = GiveawayCommands(bot)
    await cog.cog_load()
    bot.tree.remove_command = MagicMock()
    await cog.cog_unload()
