from unittest.mock import AsyncMock

import pytest

from bot.commands.quotebook import QuotebookCommands
from tests.helpers import mock_db_pool, mock_interaction


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fetch", [[], [{"id": "1", "quote_text": "Hi", "attribution": "Me", "approved": True}]]
)
async def test_quotebook_list(fetch, mock_bot):
    pool, _ = mock_db_pool(fetch=fetch)
    mock_bot.db_pool = pool
    mock_bot.cache = None
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog = QuotebookCommands(mock_bot)
    i = mock_interaction(guild_id=123, user_id=456)
    await cog.quote_group.list_cmd.callback(cog.quote_group, i)
    i.followup.send.assert_awaited()
