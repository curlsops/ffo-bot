from datetime import datetime, timezone

import pytest

from bot.commands.giveaway import parse_duration
from bot.utils.discord_helpers import discord_timestamp


class TestDiscordTimestamp:
    def test_default_format(self):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = discord_timestamp(dt)
        assert out.startswith("<t:") and ":R>" in out

    def test_custom_format(self):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = discord_timestamp(dt, "F")
        assert ":F>" in out

    @pytest.mark.parametrize("fmt", ["t", "T", "d", "D", "f", "F", "R"])
    def test_formats(self, fmt):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = discord_timestamp(dt, fmt)
        assert f":{fmt}>" in out


class TestParseDuration:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("30s", 30),
            ("5m", 300),
            ("2h", 7200),
            ("1d", 86400),
            ("1w", 604800),
            ("1H", 3600),
            ("  1h  ", 3600),
            ("0m", 0),
            ("999d", 999 * 86400),
        ],
    )
    def test_valid(self, inp, expected):
        assert parse_duration(inp) == expected

    @pytest.mark.parametrize("inp", ["abc", "1x", "", "1.5h", "x1h"])
    def test_invalid(self, inp):
        assert parse_duration(inp) is None

    @pytest.mark.parametrize("inp,expected_secs", [("1s", 1), ("60s", 60), ("10m", 600)])
    def test_more_valid(self, inp, expected_secs):
        assert parse_duration(inp) == expected_secs

    def test_1w_uppercase(self):
        assert parse_duration("1W") == 604800

    def test_59s_below_min(self):
        assert parse_duration("59s") == 59

    def test_very_large_value(self):
        result = parse_duration("9999999d")
        assert result == 9999999 * 86400


class TestParseHelpers:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, []),
            ("", []),
            ("not a role", []),
            ("<@&123> <@&456>", [123, 456]),
        ],
    )
    def test_parse_roles(self, cog, inp, expected):
        assert cog._parse_roles(inp) == expected

    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, {}),
            ("", {}),
            ("<@&123>:5,<@&456>:10", {"123": 5, "456": 10}),
            ("<@&123>:abc,<@&456>:10", {"456": 10}),
            ("<@&123>:-5", {}),
        ],
    )
    def test_parse_bonus_roles(self, cog, inp, expected):
        assert cog._parse_bonus_roles(inp) == expected

    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, None),
            ("", None),
            ("invalid", None),
            ("100", None),
            ("10,<#123>,extra", None),
            ("abc,<#123>", None),
            ("10,notachannel", None),
            ("100,<#789>", {"count": 100, "channel_id": 789}),
        ],
    )
    def test_parse_messages(self, cog, inp, expected):
        assert cog._parse_messages(inp) == expected


class TestParseMessageId:
    def test_raw_id(self, cog):
        assert cog._parse_message_id("123456789012345678") == 123456789012345678

    def test_message_link(self, cog):
        assert (
            cog._parse_message_id("https://discord.com/channels/1/2/123456789012345678")
            == 123456789012345678
        )

    @pytest.mark.parametrize("inp", ["abc", "12.34", "not-a-id", ""])
    def test_invalid(self, cog, inp):
        assert cog._parse_message_id(inp) is None

    def test_strips_whitespace(self, cog):
        assert cog._parse_message_id("  123456789012345678  ") == 123456789012345678


class TestSelectWinners:
    def test_empty_entries(self, cog):
        assert cog._select_winners([], 1) == []

    def test_zero_count(self, cog):
        assert cog._select_winners([{"user_id": 1, "entries": 1}], 0) == []

    def test_returns_requested_count(self, cog):
        list_entries = [{"user_id": index, "entries": 1} for index in range(10)]
        winners = cog._select_winners(list_entries, 2)
        assert len(winners) == 2
        assert len(set(winners)) == 2

    def test_weighted_entries(self, cog):
        list_entries = [{"user_id": 1, "entries": 5}, {"user_id": 2, "entries": 1}]
        winners = cog._select_winners(list_entries, 1)
        assert len(winners) == 1
        assert winners[0] in (1, 2)
