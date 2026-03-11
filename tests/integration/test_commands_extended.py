from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from bot.commands.polls import PollCommands
from bot.commands.privacy import PrivacyCommands
from bot.commands.reactbot import ReactBotCommands


def make_interaction(guild_id=123, user_id=456):
    i = MagicMock()
    i.guild_id = guild_id
    i.user.id = user_id
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    i.channel = MagicMock(send=AsyncMock())
    return i


@asynccontextmanager
async def _pool():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    yield conn


@pytest.mark.asyncio
@pytest.mark.parametrize("cmd_name", ["optout", "optin"])
async def test_privacy_commands(cmd_name, mock_bot):
    mock_bot.db_pool.acquire = lambda: _pool()
    i = make_interaction()
    cog = PrivacyCommands(mock_bot)
    op = app_commands.Choice(name=cmd_name.capitalize(), value=cmd_name)
    await cog.privacy_cmd.callback(i, operation=op)
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", ["1h", "6h", "1d", "3d", "7d"])
async def test_poll_durations(duration, mock_bot):
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog = PollCommands(mock_bot)
    i = make_interaction()
    await cog.poll.callback(cog, i, "Q?", "A,B,C", duration=duration)
    i.channel.send.assert_awaited()
    i.followup.send.assert_awaited_with("Poll created!", ephemeral=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase,emoji", [("hi", "👋"), ("test", "✅"), ("bye", "👋")])
async def test_reactbot_add_various_phrases(phrase, emoji):
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    @asynccontextmanager
    async def acquire():
        yield conn

    bot = MagicMock()
    bot.db_pool.acquire = acquire
    bot.cache = None
    bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.phrase_matcher.validate_pattern = AsyncMock()
    bot.phrase_matcher.invalidate_cache = MagicMock()
    bot.fetch_channel = AsyncMock(return_value=MagicMock())
    cog = ReactBotCommands(bot)
    i = make_interaction()
    op = app_commands.Choice(name="Add", value="add")
    await cog.reactbot_cmd.callback(i, operation=op, phrase=phrase, emoji=emoji)
    conn.execute.assert_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_remove_success():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"phrase": "hello", "emoji": "👋"}])

    @asynccontextmanager
    async def acquire():
        yield conn

    bot = MagicMock()
    bot.db_pool.acquire = acquire
    bot.cache = None
    bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog = ReactBotCommands(bot)
    i = make_interaction()
    op = app_commands.Choice(name="Remove", value="remove")
    await cog.reactbot_cmd.callback(i, operation=op, phrase="hello")
    conn.execute.assert_awaited()
    i.followup.send.assert_awaited()
