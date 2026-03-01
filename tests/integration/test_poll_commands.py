"""Integration tests for poll commands."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.polls import PollCommands


def make_interaction():
    i = MagicMock()
    i.guild_id = 111
    i.user.id = 222
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    i.channel = MagicMock(send=AsyncMock())
    return i


def make_bot(admin=True):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=admin)
    return bot


@pytest.mark.asyncio
async def test_poll_success():
    bot = make_bot()
    cog = PollCommands(bot)
    i = make_interaction()
    await cog.poll.callback(cog, i, "What do you prefer?", "Yes,No,Maybe", "1d")
    i.channel.send.assert_awaited_once()
    call = i.channel.send.call_args
    assert call.kwargs.get("poll") is not None
    assert call.kwargs["poll"].question == "What do you prefer?"
    assert len(call.kwargs["poll"].answers) == 3
    i.followup.send.assert_awaited_with("Poll created!", ephemeral=True)


@pytest.mark.asyncio
async def test_poll_not_admin():
    bot = make_bot(admin=False)
    cog = PollCommands(bot)
    i = make_interaction()
    await cog.poll.callback(cog, i, "Question?", "Yes,No", "1d")
    i.channel.send.assert_not_awaited()
    i.followup.send.assert_awaited_with("Admin required.", ephemeral=True)


@pytest.mark.asyncio
async def test_poll_validation_too_few_options():
    bot = make_bot()
    cog = PollCommands(bot)
    i = make_interaction()
    await cog.poll.callback(cog, i, "Question?", "OnlyOne", "1d")
    i.channel.send.assert_not_awaited()
    assert "at least 2 options" in str(i.followup.send.call_args)


@pytest.mark.asyncio
async def test_poll_validation_invalid_duration():
    bot = make_bot()
    cog = PollCommands(bot)
    i = make_interaction()
    await cog.poll.callback(cog, i, "Question?", "Yes,No", "invalid")
    i.channel.send.assert_not_awaited()
    assert "Invalid duration" in str(i.followup.send.call_args)
