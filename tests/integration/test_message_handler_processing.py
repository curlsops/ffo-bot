from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from bot.handlers.messages import MessageHandler
from tests.integration.conftest import bot_with_metrics, message_db_pool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bot_msg,guild,shutdown",
    [
        (True, MagicMock(id=1), False),
        (False, None, False),
        (False, MagicMock(id=1), True),
    ],
)
async def test_message_handler_early_returns(bot_msg, guild, shutdown):
    bot = bot_with_metrics(shutting_down=shutdown)
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = bot_msg
    msg.guild = guild
    await handler.on_message(msg)
    bot.metrics.messages_processed.labels.assert_not_called()


@pytest.mark.asyncio
async def test_message_handler_user_opted_out_skips_processing():
    db_pool, conn = message_db_pool(fetchval_result=True)
    bot = bot_with_metrics()
    bot.db_pool = db_pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[]))
    bot.voice_transcriber = None
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.content = "hello"
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = []
    await handler.on_message(msg)
    conn.execute.assert_not_awaited()
    bot.phrase_matcher.match_phrases.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transcribe_result,should_reply",
    [
        (None, False),
        ("Hello, this is a test", True),
    ],
)
async def test_message_handler_voice_transcription(transcribe_result, should_reply):
    db_pool, _ = message_db_pool(fetchval_result=None)
    bot = bot_with_metrics()
    bot.cache = None
    bot.phrase_matcher = None
    bot.db_pool = db_pool
    vt = MagicMock()
    vt.enabled = True
    vt.is_voice_attachment = MagicMock(return_value=True)
    vt.transcribe = AsyncMock(return_value=transcribe_result)
    bot.voice_transcriber = vt
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.author.display_avatar.url = "https://example.com/avatar.png"
    msg.id = 100
    msg.content = ""
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = [
        MagicMock(
            filename="voice.ogg", url="https://cdn.example.com/voice.ogg", content_type="audio/ogg"
        )
    ]
    msg.reply = AsyncMock()
    await handler.on_message(msg)
    vt.transcribe.assert_awaited_once_with("https://cdn.example.com/voice.ogg", "voice.ogg")
    if should_reply:
        msg.reply.assert_awaited_once()
        assert transcribe_result in msg.reply.call_args.kwargs["embed"].description
    else:
        msg.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_handler_non_voice_attachment_no_transcription():
    db_pool, _ = message_db_pool(fetchval_result=None)
    bot = bot_with_metrics()
    bot.phrase_matcher = None
    bot.db_pool = db_pool
    vt = MagicMock()
    vt.enabled = True
    vt.is_voice_attachment = MagicMock(return_value=False)
    vt.transcribe = AsyncMock()
    bot.voice_transcriber = vt
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = [
        MagicMock(
            filename="image.png", url="https://cdn.example.com/img.png", content_type="image/png"
        )
    ]
    msg.reply = AsyncMock()
    await handler.on_message(msg)
    vt.transcribe.assert_not_awaited()
    msg.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_handler_check_user_opt_out_error_continues_processing():
    pool, conn = message_db_pool(fetchval_result=None)
    conn.fetchval = AsyncMock(side_effect=asyncpg.PostgresConnectionError("DB"))
    bot = bot_with_metrics()
    bot.cache = None
    bot.db_pool = pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[]))
    bot.voice_transcriber = None
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.content = "hello"
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = []
    await handler.on_message(msg)
    bot.phrase_matcher.match_phrases.assert_awaited_once()
