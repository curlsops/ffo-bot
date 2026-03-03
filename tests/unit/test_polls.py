from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.polls import PollCommands, _parse_duration


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    return bot


@pytest.fixture
def cog(mock_bot):
    return PollCommands(mock_bot)


def _interaction(guild_id=1, channel_id=2, user_id=3):
    i = MagicMock(guild_id=guild_id, channel_id=channel_id)
    i.user = MagicMock(id=user_id, roles=[])
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    i.channel = MagicMock(send=AsyncMock())
    return i


class TestParseDuration:
    @pytest.mark.parametrize(
        "inp,expected_hours",
        [
            ("1h", 1),
            ("6h", 6),
            ("1d", 24),
            ("3d", 72),
            ("7d", 168),
            ("24h", 24),
            ("168h", 168),
        ],
    )
    def test_valid(self, inp, expected_hours):
        result = _parse_duration(inp)
        assert result == timedelta(hours=expected_hours)

    def test_minutes_rounds_to_hours(self):
        result = _parse_duration("30m")
        assert result == timedelta(hours=1)

    def test_minutes_60_becomes_1h(self):
        result = _parse_duration("60m")
        assert result == timedelta(hours=1)

    @pytest.mark.parametrize("inp", ["abc", "1x", "", "invalid", "1", "1.5h"])
    def test_invalid(self, inp):
        assert _parse_duration(inp) is None

    def test_case_insensitive(self):
        assert _parse_duration("1H") == timedelta(hours=1)
        assert _parse_duration("1D") == timedelta(hours=24)

    def test_whitespace_stripped(self):
        assert _parse_duration("  1h  ") == timedelta(hours=1)

    def test_boundary_168h(self):
        assert _parse_duration("168h") == timedelta(hours=168)

    def test_0h_clamped_to_1h(self):
        assert _parse_duration("0h") == timedelta(hours=1)

    @pytest.mark.parametrize("inp", ["2h", "12h", "48h"])
    def test_more_valid_hours(self, inp):
        result = _parse_duration(inp)
        assert result is not None
        assert result.total_seconds() > 0

    @pytest.mark.parametrize("inp", ["2d", "14d"])
    def test_valid_days(self, inp):
        result = _parse_duration(inp)
        assert result is not None


class TestPollCommands:
    @pytest.mark.asyncio
    async def test_check_admin_success(self, cog):
        assert await cog._check_admin(_interaction(), "poll") is True

    @pytest.mark.asyncio
    async def test_check_admin_failure(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        assert await cog._check_admin(i, "poll") is False
        i.followup.send.assert_called_with("Admin required.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_poll_question_too_long(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "X" * 301, "Yes,No", "1d")
        assert "Question too long" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_poll_too_few_options(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "Question?", "OnlyOne", "1d")
        assert "at least 2 options" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_poll_invalid_duration(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "Question?", "Yes,No", "invalid")
        assert "Invalid duration" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_poll_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        await cog.poll.callback(cog, i, "Question?", "Yes,No", "1d")
        i.followup.send.assert_called_with("Admin required.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_poll_success(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "What do you prefer?", "Yes,No,Maybe", "1d")
        i.channel.send.assert_awaited_once()
        call = i.channel.send.call_args
        assert call.kwargs.get("poll") is not None
        poll = call.kwargs["poll"]
        assert poll.question == "What do you prefer?"
        assert len(poll.answers) == 3
        i.followup.send.assert_awaited_with("Poll created!", ephemeral=True)

    @pytest.mark.asyncio
    async def test_poll_truncates_long_options(self, cog):
        i = _interaction()
        long_opt = "A" * 60
        await cog.poll.callback(cog, i, "Q?", f"Short,{long_opt}", "1d")
        call = i.channel.send.call_args
        answers = call.kwargs["poll"].answers
        assert len(answers) == 2
        assert len(answers[1].text) <= 55

    @pytest.mark.asyncio
    async def test_poll_multi_true(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "Pick many?", "A,B,C", "1d", multi=True)
        call = i.channel.send.call_args
        assert call.kwargs["poll"].multiple is True

    @pytest.mark.asyncio
    async def test_poll_channel_send_raises(self, cog):
        i = _interaction()
        i.channel.send = AsyncMock(side_effect=Exception("Permission denied"))
        await cog.poll.callback(cog, i, "Question?", "Yes,No", "1d")
        assert "Error creating poll" in str(i.followup.send.call_args)


class TestPollLongFormat:
    """Tests for auto long-format when options > 10."""

    @pytest.mark.asyncio
    async def test_poll_auto_long_when_11_options(self, cog):
        i = _interaction()
        i.channel.send = AsyncMock(return_value=MagicMock(add_reaction=AsyncMock()))
        opts = ",".join(f"Opt{i}" for i in range(11))
        await cog.poll.callback(cog, i, "Pick one?", opts, "1d")
        i.channel.send.assert_awaited_once()
        call = i.channel.send.call_args
        assert call.kwargs.get("embed") is not None
        assert call.kwargs["embed"].title == "📊 Pick one?"
        assert "Opt0" in call.kwargs["embed"].description
        assert "Opt10" in call.kwargs["embed"].description
        msg = i.channel.send.return_value
        assert msg.add_reaction.await_count == 11

    @pytest.mark.asyncio
    async def test_poll_too_few_options(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "Q?", "OnlyOne", "1d")
        assert "at least 2 options" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_poll_question_too_long(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "X" * 301, "A,B", "1d")
        assert "Question too long" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_poll_not_admin_long_format(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        opts = ",".join(f"X{i}" for i in range(11))
        await cog.poll.callback(cog, i, "Q?", opts, "1d")
        i.followup.send.assert_called_with("Admin required.", ephemeral=True)


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.polls import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
