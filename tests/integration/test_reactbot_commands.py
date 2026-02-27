"""Integration-style tests for ReactBot configuration commands."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.reactbot import ReactBotCommands


def make_interaction():
    interaction = MagicMock()
    interaction.guild_id = 123456789
    interaction.user.id = 987654321
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_db_pool(fetch_result=None, execute_result="OK"):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=fetch_result or [])
    conn.execute = AsyncMock(return_value=execute_result)

    @asynccontextmanager
    async def acquire():
        yield conn

    db_pool = MagicMock()
    db_pool.acquire = acquire
    return db_pool, conn


def make_bot():
    bot = MagicMock()

    # Rate limiter allows by default
    bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))

    # Permission checker allows admin by default
    bot.permission_checker.check_role = AsyncMock(return_value=True)

    # Phrase matcher
    bot.phrase_matcher.validate_pattern = AsyncMock()
    bot.phrase_matcher.invalidate_cache = MagicMock()

    # Metrics
    metrics = MagicMock()
    metrics.commands_executed.labels.return_value.inc = MagicMock()
    bot.metrics = metrics

    return bot


@pytest.mark.asyncio
async def test_reactbot_add_success():
    """Happy-path add command executes DB insert and audit log."""
    bot = make_bot()
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()

    await commands.reactbot_add.callback(commands, interaction, phrase=r"hello", emoji="👋")

    # Two execute calls: insert phrase_reactions + audit_log
    assert conn.execute.await_count == 2
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_add_rate_limited():
    """When rate limited, command returns early with message."""
    bot = make_bot()
    bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "slow down"))
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()

    await commands.reactbot_add.callback(commands, interaction, phrase=r"hello", emoji="👋")

    # No DB calls when rate limited
    conn.execute.assert_not_awaited()
    interaction.followup.send.assert_awaited_with("slow down", ephemeral=True)


@pytest.mark.asyncio
async def test_reactbot_list_no_rows():
    """List command handles empty result set."""
    bot = make_bot()
    db_pool, conn = make_db_pool(fetch_result=[])
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()

    await commands.reactbot_list.callback(commands, interaction)

    conn.fetch.assert_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_list_with_rows():
    """List command formats rows when present."""
    rows = [
        {"phrase": "hello", "emoji": "👋", "match_count": 5, "last_matched_at": None},
        {"phrase": "test", "emoji": "✅", "match_count": 1, "last_matched_at": None},
    ]
    bot = make_bot()
    db_pool, _ = make_db_pool(fetch_result=rows)
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()

    await commands.reactbot_list.callback(commands, interaction)

    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_remove_success():
    """Remove command deactivates phrase and invalidates cache."""
    bot = make_bot()
    db_pool, conn = make_db_pool(execute_result="UPDATE 1")
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()

    await commands.reactbot_remove.callback(commands, interaction, phrase="hello")

    conn.execute.assert_awaited()
    bot.phrase_matcher.invalidate_cache.assert_called_once_with(interaction.guild_id)
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_remove_not_found():
    """Remove command reports when no active phrase exists."""
    bot = make_bot()
    db_pool, conn = make_db_pool(execute_result="UPDATE 0")
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()

    await commands.reactbot_remove.callback(commands, interaction, phrase="missing")

    conn.execute.assert_awaited()
    interaction.followup.send.assert_awaited()
