import pytest

from bot.commands.polls import POLL_DURATIONS, _parse_duration


class TestPollParseDuration:
    @pytest.mark.parametrize(
        "s,expected_hours",
        [
            ("1m", 1),
            ("60m", 1),
            ("1h", 1),
            ("6h", 6),
            ("24h", 24),
            ("1d", 24),
            ("3d", 72),
            ("7d", 168),
        ],
    )
    def test_valid_durations(self, s, expected_hours):
        result = _parse_duration(s)
        assert result.total_seconds() == expected_hours * 3600

    @pytest.mark.parametrize(
        "s",
        [
            "",
            "x",
            "1",
            "1s",
            "1w",
            "1.5h",
            "-1h",
            "  ",
            "abc",
        ],
    )
    def test_invalid_returns_none(self, s):
        assert _parse_duration(s) is None

    def test_strips_whitespace(self):
        assert _parse_duration("  1h  ").total_seconds() == 3600

    @pytest.mark.parametrize("d", ["1H", "1D", "1M"])
    def test_case_insensitive(self, d):
        assert _parse_duration(d) is not None

    @pytest.mark.parametrize("d", POLL_DURATIONS)
    def test_all_poll_durations_parse(self, d):
        result = _parse_duration(d)
        assert result is not None
        assert result.total_seconds() > 0
