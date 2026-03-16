import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.messages import MessageHandler


def _build_message():
    msg = MagicMock()
    msg.author.id = 42
    msg.guild.id = 1
    msg.channel.id = 2
    msg.content = "hello"
    msg.attachments = [MagicMock()]
    return msg


def _build_bot():
    bot = MagicMock()
    bot.metrics = None
    bot.phrase_matcher = None
    bot.media_downloader = None
    bot.voice_transcriber = MagicMock(enabled=True)
    bot.settings = MagicMock()
    bot.settings.feature_conversion = True
    bot.settings.feature_minecraft_whitelist = False
    return bot


@pytest.mark.asyncio
async def test_handle_message_runs_independent_operations_concurrently():
    bot = _build_bot()
    handler = MessageHandler(bot)
    message = _build_message()

    gate = asyncio.Event()
    started: set[str] = set()

    async def transcribe_side_effect(_message):
        started.add("transcribe")
        await gate.wait()

    async def convert_side_effect(_message):
        started.add("convert")
        await gate.wait()

    handler._check_user_opt_out = AsyncMock(return_value=False)
    handler._transcribe_voice_messages = AsyncMock(side_effect=transcribe_side_effect)
    handler._convert_units = AsyncMock(side_effect=convert_side_effect)

    task = asyncio.create_task(handler._handle_message(message))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert started == {"transcribe", "convert"}

    gate.set()
    await task


@pytest.mark.asyncio
async def test_handle_message_serializes_db_heavy_operations():
    bot = _build_bot()
    bot.phrase_matcher = MagicMock()
    bot.media_downloader = MagicMock()
    handler = MessageHandler(bot)
    message = _build_message()

    gate = asyncio.Event()
    current_db_heavy = 0
    max_db_heavy = 0

    async def phrase_side_effect(_message):
        nonlocal current_db_heavy, max_db_heavy
        current_db_heavy += 1
        max_db_heavy = max(max_db_heavy, current_db_heavy)
        await gate.wait()
        current_db_heavy -= 1

    async def download_side_effect(_message):
        nonlocal current_db_heavy, max_db_heavy
        current_db_heavy += 1
        max_db_heavy = max(max_db_heavy, current_db_heavy)
        await gate.wait()
        current_db_heavy -= 1

    handler._check_user_opt_out = AsyncMock(return_value=False)
    handler._is_monitored_channel = AsyncMock(return_value=True)
    handler._process_phrase_matching = AsyncMock(side_effect=phrase_side_effect)
    handler._download_media = AsyncMock(side_effect=download_side_effect)
    handler._transcribe_voice_messages = AsyncMock(return_value=None)
    handler._convert_units = AsyncMock(return_value=None)

    task = asyncio.create_task(handler._handle_message(message))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    gate.set()
    await task

    assert max_db_heavy == 1
    handler._process_phrase_matching.assert_awaited_once_with(message)
    handler._download_media.assert_awaited_once_with(message)
