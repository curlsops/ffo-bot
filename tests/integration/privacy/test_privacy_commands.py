from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from bot.commands.privacy import PrivacyCommands
from tests.helpers import assert_followup_contains, mock_interaction


def _i(guild=True):
    i = MagicMock()
    i.guild_id = 111
    i.user.id = 222
    i.guild = MagicMock() if guild else None
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.followup.send = AsyncMock()
    return i


@asynccontextmanager
async def _pool(execute_raises=None):
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=execute_raises)
    yield conn


class TestPrivacy:
    def _op(self, cmd):
        return app_commands.Choice(name=cmd.capitalize(), value=cmd)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cmd", ["optout", "optin"])
    async def test_optout_optin(self, cmd):
        bot = MagicMock()
        bot.db_pool.acquire = _pool
        i = _i()
        cog = PrivacyCommands(bot)
        await cog.privacy_cmd.callback(i, operation=self._op(cmd))
        i.followup.send.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cmd", ["optout", "optin"])
    async def test_db_error(self, cmd):
        bot = MagicMock()
        bot.db_pool.acquire = lambda: _pool(Exception("DB"))
        i = _i()
        cog = PrivacyCommands(bot)
        await cog.privacy_cmd.callback(i, operation=self._op(cmd))
        assert_followup_contains(i, "error")


@asynccontextmanager
async def _fetch_pool():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    yield conn


@pytest.mark.asyncio
@pytest.mark.parametrize("cmd_name", ["optout", "optin"])
async def test_privacy_commands(cmd_name, mock_bot):
    mock_bot.db_pool.acquire = lambda: _fetch_pool()
    i = mock_interaction(guild_id=123, user_id=456)
    cog = PrivacyCommands(mock_bot)
    op = app_commands.Choice(name=cmd_name.capitalize(), value=cmd_name)
    await cog.privacy_cmd.callback(i, operation=op)
    i.followup.send.assert_awaited()
