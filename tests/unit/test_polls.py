import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.polls import (
    POLL_DURATIONS,
    PollCommands,
    _close_reaction_poll_after,
    _parse_duration,
    _poll_duration_autocomplete,
)
from tests.helpers import assert_followup_contains


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


@pytest.mark.asyncio
async def test_poll_duration_autocomplete_empty_returns_all():
    choices = await _poll_duration_autocomplete(MagicMock(), "")
    assert [c.value for c in choices] == POLL_DURATIONS


@pytest.mark.asyncio
async def test_poll_duration_autocomplete_filters():
    choices = await _poll_duration_autocomplete(MagicMock(), "1")
    assert all("1" in c.value for c in choices)


@pytest.mark.asyncio
async def test_poll_duration_autocomplete_fallback_when_no_substring_match():
    choices = await _poll_duration_autocomplete(MagicMock(), "zzz")
    assert [c.value for c in choices] == POLL_DURATIONS


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
    async def test_poll_question_too_long(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "X" * 301, "Yes,No", "1d")
        assert_followup_contains(i, "Question too long")

    @pytest.mark.asyncio
    async def test_poll_too_few_options(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "Question?", "OnlyOne", "1d")
        assert_followup_contains(i, "at least 2 options")

    @pytest.mark.asyncio
    async def test_poll_invalid_duration(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "Question?", "Yes,No", "invalid")
        assert_followup_contains(i, "Invalid duration")

    @pytest.mark.asyncio
    async def test_poll_channel_param_requires_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        target_channel = MagicMock(send=AsyncMock())
        await cog.poll.callback(cog, i, "Question?", "Yes,No", "1d", channel=target_channel)
        target_channel.send.assert_not_awaited()
        i.followup.send.assert_called_with("Admin required.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_poll_with_channel_posts_there(self, cog):
        i = _interaction()
        target_channel = MagicMock(send=AsyncMock())
        await cog.poll.callback(cog, i, "Q?", "A,B", "1d", channel=target_channel)
        target_channel.send.assert_awaited_once()
        i.channel.send.assert_not_awaited()

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
        assert_followup_contains(i, "Error creating poll")


class TestPollLongFormat:

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
        assert_followup_contains(i, "at least 2 options")

    @pytest.mark.asyncio
    async def test_poll_question_too_long(self, cog):
        i = _interaction()
        await cog.poll.callback(cog, i, "X" * 301, "A,B", "1d")
        assert_followup_contains(i, "Question too long")

    @pytest.mark.asyncio
    async def test_poll_long_format_everyone_can_create(self, cog):
        i = _interaction()
        i.channel.send = AsyncMock(return_value=MagicMock(add_reaction=AsyncMock()))
        opts = ",".join(f"X{i}" for i in range(11))
        await cog.poll.callback(cog, i, "Q?", opts, "1d")
        i.channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_poll_long_invalid_duration(self, cog):
        i = _interaction()
        i.channel.send = AsyncMock(return_value=MagicMock(add_reaction=AsyncMock()))
        opts = ",".join(f"X{i}" for i in range(11))
        await cog.poll.callback(cog, i, "Q?", opts, "invalid")
        assert_followup_contains(i, "Invalid duration")

    @pytest.mark.asyncio
    async def test_poll_long_embed_has_ends_footer(self, cog):
        i = _interaction()
        i.channel.send = AsyncMock(return_value=MagicMock(add_reaction=AsyncMock()))
        opts = ",".join(f"X{i}" for i in range(11))
        await cog.poll.callback(cog, i, "Q?", opts, "1d")
        embed = i.channel.send.call_args.kwargs["embed"]
        assert embed.footer.text is not None
        assert "Ends" in embed.footer.text
        assert "<t:" in embed.footer.text

    @pytest.mark.asyncio
    async def test_poll_long_schedules_close_task(self, cog):
        i = _interaction()
        i.channel.send = AsyncMock(return_value=MagicMock(add_reaction=AsyncMock(), id=999))
        opts = ",".join(f"X{i}" for i in range(11))
        real_create_task = asyncio.create_task

        def mock_create_task(coro):
            task = real_create_task(coro)
            task.cancel()
            return task

        with patch(
            "bot.commands.polls.asyncio.create_task", side_effect=mock_create_task
        ) as create_task:
            await cog.poll.callback(cog, i, "Q?", opts, "1d")
            create_task.assert_called_once()
            coro = create_task.call_args[0][0]
            assert coro.cr_code.co_name == "_close_reaction_poll_after"


class TestCloseReactionPollAfter:
    @pytest.mark.asyncio
    async def test_edits_embed_with_results_and_clears_reactions(self):
        channel = MagicMock()
        msg = MagicMock()
        msg.reactions = [
            MagicMock(emoji="1️⃣", count=4),
            MagicMock(emoji="2️⃣", count=2),
            MagicMock(emoji="3️⃣", count=1),
        ]
        msg.edit = AsyncMock()
        msg.clear_reactions = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=msg)

        opts = ["Alpha", "Beta", "Gamma"]
        emojis = ["1️⃣", "2️⃣", "3️⃣"]
        delta = timedelta(seconds=0)

        with patch("bot.commands.polls.asyncio.sleep", new_callable=AsyncMock):
            await _close_reaction_poll_after(channel, 123, delta, opts, emojis, "Pick one?")

        channel.fetch_message.assert_awaited_once_with(123)
        msg.edit.assert_awaited_once()
        edit_embed = msg.edit.call_args.kwargs["embed"]
        assert "Pick one?" in edit_embed.title
        assert "*Poll ended*" in edit_embed.description
        assert "Alpha — 3" in edit_embed.description
        assert "Beta — 1" in edit_embed.description
        assert "Gamma — 0" in edit_embed.description
        assert edit_embed.footer.text == "Poll ended"
        msg.clear_reactions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_when_close_poll_fails(self, caplog):
        import logging

        channel = MagicMock()
        channel.fetch_message = AsyncMock(side_effect=RuntimeError("gone"))
        with caplog.at_level(logging.WARNING):
            with patch("bot.commands.polls.asyncio.sleep", new_callable=AsyncMock):
                await _close_reaction_poll_after(
                    channel,
                    1,
                    timedelta(seconds=0),
                    ["A"],
                    ["1️⃣"],
                    "Q?",
                )
        assert "Failed to close reaction poll" in caplog.text


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.polls import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
