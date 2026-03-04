"""Tests for giveaway parse_duration and build_embed."""

from datetime import datetime, timezone

import discord
import pytest

from bot.commands.giveaway import (
    GIVEAWAY_DURATIONS,
    TIME_UNITS,
    build_embed,
    parse_duration,
)


class TestParseDuration:
    @pytest.mark.parametrize(
        "duration,expected",
        [
            ("1s", 1),
            ("60s", 60),
            ("1m", 60),
            ("5m", 300),
            ("1h", 3600),
            ("24h", 86400),
            ("1d", 86400),
            ("7d", 604800),
            ("1w", 604800),
            ("2w", 1209600),
            ("30s", 30),
            ("90s", 90),
            ("2m", 120),
            ("12h", 43200),
            ("3d", 259200),
        ],
    )
    def test_valid_durations(self, duration, expected):
        assert parse_duration(duration) == expected

    @pytest.mark.parametrize(
        "duration",
        [
            "",
            "x",
            "1",
            "1x",
            "1 s",
            "1.5m",
            "-1m",
            "abc",
            "1m2s",
            "  ",
        ],
    )
    def test_invalid_durations_return_none(self, duration):
        assert parse_duration(duration) is None

    @pytest.mark.parametrize("unit,mult", list(TIME_UNITS.items()))
    def test_all_units(self, unit, mult):
        result = parse_duration(f"1{unit}")
        assert result == mult

    def test_strips_whitespace(self):
        assert parse_duration("  5m  ") == 300

    def test_case_insensitive(self):
        assert parse_duration("1M") == 60
        assert parse_duration("1H") == 3600
        assert parse_duration("1D") == 86400
        assert parse_duration("1W") == 604800


class TestBuildEmbed:
    def _minimal_giveaway(self, **overrides):
        base = {
            "prize": "Test Prize",
            "host_id": 123456789,
            "ends_at": datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        }
        base.update(overrides)
        return base

    def test_basic_embed(self):
        g = self._minimal_giveaway()
        embed = build_embed(g, 0)
        assert embed.title == "🎉 GIVEAWAY 🎉"
        assert "Test Prize" in embed.description
        assert "<@123456789>" in embed.description
        assert embed.color == discord.Color.gold()

    def test_ended_embed(self):
        g = self._minimal_giveaway()
        g["ended_at"] = g["ends_at"]
        embed = build_embed(g, 5, ended=True)
        assert embed.title == "🎉 GIVEAWAY ENDED 🎉"
        assert embed.color == discord.Color.dark_grey()

    def test_with_donor(self):
        g = self._minimal_giveaway(donor_id=999)
        embed = build_embed(g, 0)
        assert "Donated by" in embed.description
        assert "<@999>" in embed.description

    def test_with_extra_text(self):
        g = self._minimal_giveaway(extra_text="Good luck everyone!")
        embed = build_embed(g, 0)
        assert "Good luck everyone!" in embed.description

    def test_with_image_url(self):
        g = self._minimal_giveaway(image_url="https://example.com/img.png")
        embed = build_embed(g, 0)
        assert embed.image.url == "https://example.com/img.png"

    def test_single_winner_footer(self):
        g = self._minimal_giveaway(winners_count=1)
        g["ended_at"] = g["ends_at"]
        embed = build_embed(g, 3, ended=True)
        assert "1 winner" in embed.footer.text
        assert "3 entries" in embed.footer.text

    def test_multiple_winners_footer(self):
        g = self._minimal_giveaway(winners_count=5)
        g["ended_at"] = g["ends_at"]
        embed = build_embed(g, 10, ended=True)
        assert "5 winners" in embed.footer.text
        assert "10 entries" in embed.footer.text

    def test_uses_ended_at_when_present(self):
        ended = datetime(2025, 2, 28, 10, 0, 0, tzinfo=timezone.utc)
        g = self._minimal_giveaway(ends_at=ended, ended_at=ended)
        embed = build_embed(g, 0, ended=True)
        assert embed.timestamp == ended

    @pytest.mark.parametrize("entry_count", [0, 1, 100, 1000])
    def test_various_entry_counts(self, entry_count):
        g = self._minimal_giveaway()
        g["ended_at"] = g["ends_at"]
        embed = build_embed(g, entry_count, ended=True)
        assert str(entry_count) in embed.footer.text


class TestGiveawayDurations:
    def test_durations_non_empty(self):
        assert len(GIVEAWAY_DURATIONS) > 0

    def test_durations_all_parseable(self):
        for d in GIVEAWAY_DURATIONS:
            assert parse_duration(d) is not None, f"{d} should parse"

    def test_durations_fit_autocomplete(self):
        assert len(GIVEAWAY_DURATIONS) <= 25
