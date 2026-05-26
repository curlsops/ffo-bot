from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from bot.commands.giveaway import GiveawayCommands
from tests.helpers import assert_followup_contains, db_pool_with_conn, mock_interaction

_OP_REROLL = app_commands.Choice(name="Reroll", value="reroll")
_OP_START = app_commands.Choice(name="Start", value="start")


def make_bot(admin=True):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=admin)
    return bot


@pytest.mark.asyncio
async def test_reroll_success():
    giveaway = {
        "id": 1,
        "is_active": False,
        "message_id": 123456789012345678,
        "channel_id": 2,
        "prize": "Test Prize",
        "winners_count": 1,
        "ended_at": datetime.now(timezone.utc),
    }
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value=giveaway),
        fetch=AsyncMock(
            side_effect=[
                [{"user_id": 10, "entries": 1}, {"user_id": 20, "entries": 1}],
                [],
            ]
        ),
        execute=AsyncMock(),
        executemany=AsyncMock(),
    )
    bot = make_bot()
    bot.db_pool = db_pool_with_conn(conn)
    bot.get_channel = MagicMock(return_value=None)

    cog = GiveawayCommands(bot)
    i = mock_interaction(guild_id=111, user_id=222)
    await cog.giveaway_cmd.callback(i, operation=_OP_REROLL, message_id="123456789012345678")

    conn.execute.assert_awaited()
    i.followup.send.assert_awaited()
    assert_followup_contains(i, "Rerolled")


@pytest.mark.asyncio
async def test_reroll_not_found():
    conn = AsyncMock(fetchrow=AsyncMock(return_value=None))
    bot = make_bot()
    bot.db_pool = db_pool_with_conn(conn)

    cog = GiveawayCommands(bot)
    i = mock_interaction(guild_id=111, user_id=222)
    await cog.giveaway_cmd.callback(i, operation=_OP_REROLL, message_id="123456789012345678")

    assert_followup_contains(i, "not found")


@pytest.mark.asyncio
async def test_reroll_still_active():
    giveaway = {
        "id": 1,
        "is_active": True,
        "message_id": 123456789012345678,
    }
    conn = AsyncMock(fetchrow=AsyncMock(return_value=giveaway))
    bot = make_bot()
    bot.db_pool = db_pool_with_conn(conn)

    cog = GiveawayCommands(bot)
    i = mock_interaction(guild_id=111, user_id=222)
    await cog.giveaway_cmd.callback(i, operation=_OP_REROLL, message_id="123456789012345678")

    assert_followup_contains(i, "still active")


@pytest.mark.asyncio
async def test_reroll_invalid_message_id():
    conn = AsyncMock()
    bot = make_bot()
    bot.db_pool = db_pool_with_conn(conn)

    cog = GiveawayCommands(bot)
    i = mock_interaction(guild_id=111, user_id=222)
    await cog.giveaway_cmd.callback(i, operation=_OP_REROLL, message_id="not-a-valid-id")

    assert_followup_contains(i, "Invalid message ID")
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_gstart_with_role_constraints():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    bot = make_bot()
    bot.db_pool = db_pool_with_conn(conn)
    bot.metrics = MagicMock()
    bot.metrics.commands_executed.labels.return_value.inc = MagicMock()
    bot.notifier = None
    cog = GiveawayCommands(bot)
    i = mock_interaction(guild_id=111, user_id=222)
    i.channel_id = 222
    i.followup.send = AsyncMock(return_value=MagicMock(id=999))
    await cog.giveaway_cmd.callback(
        i,
        operation=_OP_START,
        duration="1h",
        winners=1,
        prize="Test Prize",
        required_roles="<@&123>",
        blacklist_roles="<@&456>",
        bonus_roles="<@&123>:5",
    )
    args = conn.execute.call_args_list[0][0]
    assert [123] == args[9]
    assert [456] == args[10]
    assert {"123": 5} == args[12]
