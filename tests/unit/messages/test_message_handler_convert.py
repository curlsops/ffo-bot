from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.messages import MessageHandler


@pytest.fixture
def handler():
    bot = MagicMock()
    bot.is_shutting_down.return_value = False
    bot.settings = MagicMock()
    bot.settings.feature_conversion = True
    bot.metrics = None
    bot.phrase_matcher = None
    bot.voice_transcriber = None
    return MessageHandler(bot)


@pytest.fixture
def message():
    m = MagicMock()
    m.author.bot = False
    m.guild = MagicMock(id=1)
    m.channel = MagicMock()
    m.content = "I weigh 10 lb"
    m.author.display_name = "TestUser"
    m.reply = AsyncMock()
    return m


@pytest.mark.asyncio
async def test_convert_units_replies_when_imperial_detected(handler, message):
    await handler._convert_units(message)
    message.reply.assert_awaited_once()
    call_args = message.reply.call_args
    assert call_args.kwargs.get("mention_author") is False
    embed = call_args.kwargs.get("embed")
    assert embed is not None
    assert "4.54 kg" in embed.description
    assert "I weigh" in embed.description


@pytest.mark.asyncio
async def test_convert_units_no_reply_when_no_imperial(handler, message):
    message.content = "Hello world"
    with patch("bot.processors.unit_converter.detect_and_convert", return_value=None):
        await handler._convert_units(message)
    message.reply.assert_not_awaited()
