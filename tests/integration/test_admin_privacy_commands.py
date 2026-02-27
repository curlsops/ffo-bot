"""Tests for admin and privacy command cogs."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.admin import AdminCommands
from bot.commands.privacy import PrivacyCommands


def make_interaction():
    interaction = MagicMock()
    interaction.guild_id = 111
    interaction.user.id = 222
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_db_pool():
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="OK")

    @asynccontextmanager
    async def acquire():
        yield conn

    db_pool = MagicMock()
    db_pool.acquire = acquire
    return db_pool, conn


@pytest.mark.asyncio
async def test_admin_ping_uses_latency_and_sends_message():
    """Ping command sends a response including latency."""
    bot = MagicMock()
    bot.latency = 0.123  # 123 ms
    cog = AdminCommands(bot)
    interaction = make_interaction()

    await cog.ping.callback(cog, interaction)

    interaction.response.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_privacy_optout_executes_queries_and_sends_confirmation():
    """privacy_optout writes preference, deletes metadata, and replies."""
    bot = MagicMock()
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    cog = PrivacyCommands(bot)
    interaction = make_interaction()

    await cog.privacy_optout.callback(cog, interaction)

    # Two execute calls inside a single DB context
    assert conn.execute.await_count == 2
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_privacy_optin_executes_query_and_sends_confirmation():
    """privacy_optin clears opt-out flag and replies."""
    bot = MagicMock()
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    cog = PrivacyCommands(bot)
    interaction = make_interaction()

    await cog.privacy_optin.callback(cog, interaction)

    conn.execute.assert_awaited()
    interaction.followup.send.assert_awaited()

