import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.handlers.messages import MessageHandler


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


def _bot_with_metrics(shutting_down=False):
    bot = MagicMock()
    bot.is_shutting_down.return_value = shutting_down
    bot.metrics = MagicMock()
    bot.metrics.messages_processed.labels.return_value.inc = MagicMock()
    return bot


@pytest.mark.asyncio
async def test_message_handler_processes_phrase_match():
    bot = MagicMock()
    bot.is_shutting_down.return_value = False
    bot.cache = None
    metrics = MagicMock()
    metrics.messages_processed.labels.return_value.inc = MagicMock()
    metrics.phrase_matches.labels.return_value.inc = MagicMock()
    metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.metrics = metrics
    bot.phrase_matcher.match_phrases = AsyncMock(return_value=[("id-1", "✅")])
    db_pool, conn = make_db_pool()
    conn.executemany = AsyncMock()
    bot.db_pool = db_pool

    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.id = 100
    msg.content = "test message"
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = []
    msg.add_reaction = AsyncMock()

    await handler.on_message(msg)

    metrics.messages_processed.labels.assert_called_once()
    metrics.phrase_matches.labels.assert_called_once()
    msg.add_reaction.assert_awaited()
    conn.executemany.assert_awaited_once()
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_message_handler_phrase_match_log_failure_still_reacts(caplog):
    caplog.set_level(logging.WARNING, logger="bot.handlers.messages")
    db_pool, conn = make_db_pool()
    conn.executemany = AsyncMock(side_effect=Exception("DB down"))
    bot = MagicMock()
    bot.is_shutting_down.return_value = False
    bot.cache = None
    bot.metrics = MagicMock()
    bot.metrics.messages_processed.labels.return_value.inc = MagicMock()
    bot.metrics.phrase_matches.labels.return_value.inc = MagicMock()
    bot.phrase_matcher.match_phrases = AsyncMock(return_value=[("id-1", "✅")])
    bot.db_pool = db_pool
    bot.voice_transcriber = None
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.id = 100
    msg.content = "test"
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = []
    msg.add_reaction = AsyncMock()
    await handler.on_message(msg)
    msg.add_reaction.assert_awaited_once()
    assert "Phrase matching error" in caplog.text


@pytest.mark.asyncio
async def test_message_edit_phrase_matching_removes_stale_reaction():
    db_pool, _ = make_db_pool(fetchval_result=None)
    bot = _bot_with_metrics()
    bot.cache = None
    bot.db_pool = db_pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[]))
    bot.user = MagicMock()
    bot.user.id = 999

    reaction = MagicMock()
    reaction.emoji = "👋"
    reaction.me = True
    fetched_msg = MagicMock()
    fetched_msg.id = 100
    fetched_msg.reactions = [reaction]
    fetched_msg.remove_reaction = AsyncMock()
    fetched_msg.add_reaction = AsyncMock()

    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=fetched_msg)

    before = MagicMock()
    before.content = "hello"
    after = MagicMock()
    after.content = "goodbye"
    after.author.bot = False
    after.author.id = 42
    after.guild.id = 1
    after.channel = channel
    after.channel.id = 2
    after.id = 100

    handler = MessageHandler(bot)
    await handler.on_message_edit(before, after)

    bot.phrase_matcher.match_phrases.assert_awaited_once_with("goodbye", 1)
    fetched_msg.remove_reaction.assert_awaited_once_with("👋", bot.user)
    fetched_msg.add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_edit_phrase_matching_adds_new_reaction():
    db_pool, _ = make_db_pool(fetchval_result=None)
    bot = _bot_with_metrics()
    bot.cache = None
    bot.metrics.phrase_matches = MagicMock()
    bot.metrics.phrase_matches.labels.return_value.inc = MagicMock()
    bot.db_pool = db_pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[("id-1", "👋")]))
    bot.user = MagicMock()
    bot.user.id = 999

    fetched_msg = MagicMock()
    fetched_msg.id = 100
    fetched_msg.reactions = []
    fetched_msg.remove_reaction = AsyncMock()
    fetched_msg.add_reaction = AsyncMock()

    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=fetched_msg)

    before = MagicMock()
    before.content = "hi"
    after = MagicMock()
    after.content = "hello"
    after.author.bot = False
    after.author.id = 42
    after.guild.id = 1
    after.channel = channel
    after.id = 100

    handler = MessageHandler(bot)
    await handler.on_message_edit(before, after)

    fetched_msg.remove_reaction.assert_not_awaited()
    fetched_msg.add_reaction.assert_awaited_once_with("👋")


@pytest.mark.asyncio
async def test_message_edit_phrase_matching_skips_when_content_unchanged():
    db_pool, _ = make_db_pool(fetchval_result=None)
    bot = _bot_with_metrics()
    bot.db_pool = db_pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[]))
    handler = MessageHandler(bot)
    before = MagicMock()
    before.content = "hello"
    after = MagicMock()
    after.content = "hello"
    await handler.on_message_edit(before, after)
    bot.phrase_matcher.match_phrases.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_edit_phrase_matching_fetch_not_found_returns_early():
    db_pool, _ = make_db_pool(fetchval_result=None)
    bot = _bot_with_metrics()
    bot.cache = None
    bot.db_pool = db_pool
    bot.user = MagicMock()
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[("id-1", "👋")]))

    channel = MagicMock()
    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

    before = MagicMock()
    before.content = "hi"
    after = MagicMock()
    after.content = "hello"
    after.author.bot = False
    after.author.id = 42
    after.guild.id = 1
    after.channel = channel
    after.id = 100

    handler = MessageHandler(bot)
    await handler.on_message_edit(before, after)

    channel.fetch_message.assert_awaited_once_with(100)


@pytest.mark.asyncio
async def test_message_edit_phrase_matching_skips_bot_message():
    db_pool, _ = make_db_pool(fetchval_result=None)
    bot = _bot_with_metrics()
    bot.db_pool = db_pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[]))
    handler = MessageHandler(bot)
    before = MagicMock()
    before.content = "a"
    after = MagicMock()
    after.content = "b"
    after.author.bot = True
    after.guild = MagicMock()
    await handler.on_message_edit(before, after)
    bot.phrase_matcher.match_phrases.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_handler_phrase_match_http_exception_logged(caplog):
    caplog.set_level(logging.WARNING, logger="bot.handlers.messages")
    bot = MagicMock()
    bot.is_shutting_down.return_value = False
    bot.cache = None
    bot.metrics = MagicMock()
    bot.metrics.messages_processed.labels.return_value.inc = MagicMock()
    bot.phrase_matcher.match_phrases = AsyncMock(return_value=[("id-1", "✅")])
    db_pool, _ = make_db_pool()
    bot.db_pool = db_pool
    bot.voice_transcriber = None
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.id = 100
    msg.content = "test"
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = []
    msg.add_reaction = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
    await handler.on_message(msg)
    assert "Failed to add reaction" in caplog.text or "HTTPException" in caplog.text
