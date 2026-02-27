"""Tests for reaction and message handlers."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.messages import MessageHandler
from bot.handlers.reactions import ReactionHandler


def make_db_pool(fetchval_result=None):
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=fetchval_result)
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


@pytest.mark.asyncio
async def test_message_handler_processes_user_message_with_phrase_match():
    """on_message runs phrase matching and logs matches for normal user message."""
    bot = MagicMock()
    bot.is_shutting_down.return_value = False

    # Metrics
    metrics = MagicMock()
    metrics.messages_processed.labels.return_value.inc = MagicMock()
    metrics.phrase_matches.labels.return_value.inc = MagicMock()
    metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.metrics = metrics

    # Phrase matcher
    bot.phrase_matcher.match_phrases = AsyncMock(return_value=[("id-1", "✅")])

    # DB pool for _log_phrase_match
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool

    # Media downloader off for this test
    bot.media_downloader = None

    handler = MessageHandler(bot)

    # Fake message
    message = MagicMock()
    message.author.bot = False
    message.author.id = 42
    message.id = 100
    message.content = "test message"
    message.guild.id = 1
    message.channel.id = 2
    message.attachments = []
    message.add_reaction = AsyncMock()

    await handler.on_message(message)

    metrics.messages_processed.labels.assert_called_once()
    metrics.phrase_matches.labels.assert_called_once()
    message.add_reaction.assert_awaited()
    # Two execute calls from _log_phrase_match
    assert conn.execute.await_count == 2


@pytest.mark.asyncio
async def test_reaction_handler_add_assigns_role():
    """on_raw_reaction_add fetches role and adds it to member."""
    bot = MagicMock()
    metrics = MagicMock()
    metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.metrics = metrics

    # DB pool returns role_id
    db_pool, conn = make_db_pool(fetchval_result=1234)
    bot.db_pool = db_pool

    # Guild / member / role
    role = MagicMock()
    role.id = 1234
    role.name = "TestRole"

    member = MagicMock()
    member.add_roles = AsyncMock()

    guild = MagicMock()
    guild.id = 1
    guild.get_member.return_value = member
    guild.get_role.return_value = role

    bot.get_guild.return_value = guild
    bot.user.id = 999

    handler = ReactionHandler(bot)

    payload = MagicMock()
    payload.user_id = 10
    payload.guild_id = 1
    payload.message_id = 55
    payload.emoji = "✅"

    await handler.on_raw_reaction_add(payload)

    conn.fetchval.assert_awaited()
    member.add_roles.assert_awaited()

