from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from bot.commands.polls import PollCommands
from bot.commands.privacy import PrivacyCommands
from tests.helpers import mock_interaction


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
    i = mock_interaction(guild_id=123, user_id=456)
    cog = PrivacyCommands(mock_bot)
    op = app_commands.Choice(name=cmd_name.capitalize(), value=cmd_name)
    await cog.privacy_cmd.callback(i, operation=op)
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", ["1h", "6h", "1d", "3d", "7d"])
async def test_poll_durations(duration, mock_bot):
    cog = PollCommands(mock_bot)
    i = mock_interaction(guild_id=123, user_id=456)
    i.channel.send = AsyncMock()
    await cog.poll.callback(cog, i, "Q?", "A,B,C", duration=duration)
    i.channel.send.assert_awaited()
    i.followup.send.assert_awaited_with("Poll created!", ephemeral=True)
