from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.giveaway import GiveawayCommands


def make_interaction():
    i = MagicMock()
    i.guild_id = 111
    i.user.id = 222
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


def make_bot(admin=True):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=admin)
    return bot


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_greroll_success():
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
    bot.db_pool = _db_ctx(conn)
    bot.get_channel = MagicMock(return_value=None)

    cog = GiveawayCommands(bot)
    i = make_interaction()
    group = cog.giveaway_group
    await group.reroll_cmd.callback(group, i, "123456789012345678")

    conn.execute.assert_awaited()
    i.followup.send.assert_awaited()
    assert "Rerolled" in str(i.followup.send.call_args)


@pytest.mark.asyncio
async def test_greroll_not_found():
    conn = AsyncMock(fetchrow=AsyncMock(return_value=None))
    bot = make_bot()
    bot.db_pool = _db_ctx(conn)

    cog = GiveawayCommands(bot)
    i = make_interaction()
    group = cog.giveaway_group
    await group.reroll_cmd.callback(group, i, "123456789012345678")

    assert "not found" in str(i.followup.send.call_args)


@pytest.mark.asyncio
async def test_greroll_still_active():
    giveaway = {
        "id": 1,
        "is_active": True,
        "message_id": 123456789012345678,
    }
    conn = AsyncMock(fetchrow=AsyncMock(return_value=giveaway))
    bot = make_bot()
    bot.db_pool = _db_ctx(conn)

    cog = GiveawayCommands(bot)
    i = make_interaction()
    group = cog.giveaway_group
    await group.reroll_cmd.callback(group, i, "123456789012345678")

    assert "still active" in str(i.followup.send.call_args)


@pytest.mark.asyncio
async def test_greroll_invalid_message_id():
    conn = AsyncMock()
    bot = make_bot()
    bot.db_pool = _db_ctx(conn)

    cog = GiveawayCommands(bot)
    i = make_interaction()
    group = cog.giveaway_group
    await group.reroll_cmd.callback(group, i, "not-a-valid-id")

    assert "Invalid message ID" in str(i.followup.send.call_args)
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_gstart_with_role_constraints():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    bot = make_bot()
    bot.db_pool = _db_ctx(conn)
    bot.metrics = MagicMock()
    bot.metrics.commands_executed.labels.return_value.inc = MagicMock()
    bot.notifier = None
    cog = GiveawayCommands(bot)
    i = make_interaction()
    i.guild_id = 111
    i.channel_id = 222
    i.user.id = 333
    i.followup.send = AsyncMock(return_value=MagicMock(id=999))
    group = cog.giveaway_group
    await group.start_cmd.callback(
        group,
        i,
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
