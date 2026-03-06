from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.quotebook import QuotebookCommands


def make_interaction(guild_id=123, user_id=456):
    i = MagicMock()
    i.guild_id = guild_id
    i.user.id = user_id
    i.user.mention = "<@456>"
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


@asynccontextmanager
async def _pool(fetch=None, fetchrow=None):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow or {})
    conn.execute = AsyncMock()
    yield conn


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fetch", [[], [{"id": "1", "quote_text": "Hi", "attribution": "Me", "approved": True}]]
)
async def test_quotebook_list(fetch, mock_bot):
    mock_bot.db_pool.acquire = lambda: _pool(fetch=fetch)
    mock_bot.cache = None
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog = QuotebookCommands(mock_bot)
    i = make_interaction()
    await cog.quote_group.list_cmd.callback(cog.quote_group, i)
    i.followup.send.assert_awaited()
