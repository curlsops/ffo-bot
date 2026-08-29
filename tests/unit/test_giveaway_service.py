from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.giveaway_service import (
    build_embed,
    build_end_announcement,
    build_ended_embed,
    build_reroll_announcement,
    finalize_and_announce,
    format_winner_mentions,
    select_winners,
)


def _giveaway(**overrides):
    base = {
        "prize": "Prize",
        "host_id": 123,
        "donor_id": None,
        "winners_count": 2,
        "ends_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


class TestSelectWinners:
    def test_selects_distinct_winners(self):
        entries = [{"user_id": idx, "entries": 1} for idx in range(4)]
        winners = select_winners(entries, 2)
        assert len(winners) == 2
        assert len(set(winners)) == 2


class TestAnnouncementFormatting:
    def test_format_winner_mentions(self):
        assert format_winner_mentions([10, 20]) == "<@10> <@20>"

    def test_end_announcement_with_winners(self):
        text = build_end_announcement("Prize", [1, 2])
        assert "Congratulations" in text
        assert "<@1> <@2>" in text

    def test_end_announcement_without_winners(self):
        assert build_end_announcement("Prize", []) == "No entries for **Prize**. No winners."

    def test_reroll_announcement_with_winners(self):
        text = build_reroll_announcement("Prize", [3])
        assert text == "🎉 Reroll! New winners for **Prize**: <@3>"

    def test_reroll_announcement_without_winners(self):
        assert build_reroll_announcement("Prize", []) == "Reroll for **Prize** — no valid entries."


class TestEmbedFormatting:
    def test_build_embed_ended_footer_uses_configured_winners_count(self):
        embed = build_embed(_giveaway(winners_count=3), 8, ended=True)
        assert embed.title == "🎉 GIVEAWAY ENDED 🎉"
        assert embed.footer.text == "3 winners • 8 entries"

    def test_build_ended_embed_has_winners_field(self):
        embed = build_ended_embed(_giveaway(), [10, 20], 5)
        assert embed.fields[0].name == "Winners"
        assert "<@10>" in embed.fields[0].value
        assert "<@20>" in embed.fields[0].value
        assert embed.footer.text == "2 winners • 5 entries"

    def test_build_ended_embed_no_winners(self):
        embed = build_ended_embed(_giveaway(), [], 0)
        assert embed.fields[0].value == "No valid entries"
        assert embed.footer.text == "0 entries"

    def test_build_ended_embed_includes_donor(self):
        embed = build_ended_embed(_giveaway(donor_id=555), [100], 5)
        assert "Donated by" in embed.description and "<@555>" in embed.description


def _giveaway_with_ids(**overrides):
    return _giveaway(id="gid-1", channel_id=10, message_id=20, **overrides)


class TestFinalizeAndAnnounce:
    @pytest.mark.asyncio
    async def test_edits_message_and_sends_announcement(self):
        bot = MagicMock()
        channel = MagicMock()
        msg = MagicMock()
        msg.edit = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=msg)
        channel.send = AsyncMock()
        bot.get_channel.return_value = channel
        giveaway = _giveaway_with_ids()

        await finalize_and_announce(bot, giveaway, [1, 2], 5, "Announcement text")

        msg.edit.assert_awaited_once()
        assert msg.edit.call_args.kwargs["view"] is None
        embed = msg.edit.call_args.kwargs["embed"]
        assert embed.fields[0].name == "Winners"
        channel.send.assert_awaited_once_with("Announcement text")

    @pytest.mark.asyncio
    async def test_returns_resolved_channel_for_caller_follow_up(self):
        bot = MagicMock()
        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=MagicMock(edit=AsyncMock()))
        channel.send = AsyncMock()
        bot.get_channel.return_value = channel
        giveaway = _giveaway_with_ids()

        result = await finalize_and_announce(bot, giveaway, [1], 1, "text")

        assert result is channel

    @pytest.mark.asyncio
    async def test_channel_not_found_logs_and_returns(self, caplog):
        import logging as std_logging

        caplog.set_level(std_logging.WARNING, logger="bot.services.giveaway_service")
        bot = MagicMock()
        bot.get_channel.return_value = None
        bot.fetch_channel = AsyncMock(side_effect=Exception("not found"))
        giveaway = _giveaway_with_ids()

        await finalize_and_announce(bot, giveaway, [1], 1, "text")

        assert "Could not fetch channel" in caplog.text
        assert (await finalize_and_announce(bot, giveaway, [1], 1, "text")) is None

    @pytest.mark.asyncio
    async def test_message_not_found_still_sends_announcement(self):
        bot = MagicMock()
        channel = MagicMock()
        channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(status=404), "message deleted")
        )
        channel.send = AsyncMock()
        bot.get_channel.return_value = channel
        giveaway = _giveaway_with_ids()

        await finalize_and_announce(bot, giveaway, [1], 1, "Announcement text")

        channel.send.assert_awaited_once_with("Announcement text")
