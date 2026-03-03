from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import discord
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


def _bot_with_metrics(shutting_down=False):
    bot = MagicMock()
    bot.is_shutting_down.return_value = shutting_down
    bot.metrics = MagicMock()
    bot.metrics.messages_processed.labels.return_value.inc = MagicMock()
    return bot


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
    bot = _bot_with_metrics(shutting_down=shutdown)
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = bot_msg
    msg.guild = guild
    await handler.on_message(msg)
    bot.metrics.messages_processed.labels.assert_not_called()


@pytest.mark.asyncio
async def test_message_handler_user_opted_out_skips_processing():
    db_pool, conn = make_db_pool(fetchval_result=True)
    bot = _bot_with_metrics()
    bot.db_pool = db_pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[]))
    bot.media_downloader = None
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
    db_pool, _ = make_db_pool(fetchval_result=None)
    bot = _bot_with_metrics()
    bot.phrase_matcher = None
    bot.media_downloader = None
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
@pytest.mark.parametrize(
    "monitored_config,should_download",
    [
        ({"monitored_channels": {"2": True}}, True),
        ({"monitored_channels": {"999": True}}, False),
        (None, False),
        ({}, False),
    ],
)
async def test_message_handler_monitored_channel_media_download(monitored_config, should_download):
    conn = MagicMock()
    conn.fetchval = AsyncMock(side_effect=[None, monitored_config])
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    bot = _bot_with_metrics()
    bot.db_pool = pool
    bot.phrase_matcher = None
    bot.voice_transcriber = None
    md = MagicMock()
    md.download_media = AsyncMock()
    bot.media_downloader = md
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.id = 100
    msg.content = ""
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = [MagicMock(url="u", filename="x.png", content_type="image/png", size=100)]
    await handler.on_message(msg)
    if should_download:
        md.download_media.assert_awaited_once()
    else:
        md.download_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_handler_non_voice_attachment_no_transcription():
    db_pool, _ = make_db_pool(fetchval_result=None)
    bot = _bot_with_metrics()
    bot.phrase_matcher = None
    bot.media_downloader = None
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
async def test_message_handler_media_download_error_logged():
    conn = MagicMock()
    conn.fetchval = AsyncMock(side_effect=[None, {"monitored_channels": {"2": True}}])
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    bot = _bot_with_metrics()
    bot.metrics.errors_total = MagicMock()
    bot.metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.db_pool = pool
    bot.phrase_matcher = None
    bot.voice_transcriber = None
    md = MagicMock()
    md.download_media = AsyncMock(side_effect=Exception("download failed"))
    bot.media_downloader = md
    handler = MessageHandler(bot)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 42
    msg.id = 100
    msg.content = ""
    msg.guild.id = 1
    msg.channel.id = 2
    msg.attachments = [MagicMock(url="u", filename="x.png", content_type="image/png", size=100)]
    await handler.on_message(msg)
    bot.metrics.errors_total.labels.assert_called_with(error_type="media_download")
    bot.metrics.errors_total.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_message_handler_processes_phrase_match():
    bot = MagicMock()
    bot.is_shutting_down.return_value = False
    metrics = MagicMock()
    metrics.messages_processed.labels.return_value.inc = MagicMock()
    metrics.phrase_matches.labels.return_value.inc = MagicMock()
    metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.metrics = metrics
    bot.phrase_matcher.match_phrases = AsyncMock(return_value=[("id-1", "✅")])
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    bot.media_downloader = None

    handler = MessageHandler(bot)
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
    assert conn.execute.await_count == 2


@pytest.mark.asyncio
async def test_reaction_handler_add_assigns_role():
    bot = MagicMock()
    bot.cache = None
    bot.settings = MagicMock(feature_minecraft_whitelist=False)
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    metrics = MagicMock()
    metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.metrics = metrics
    db_pool, conn = make_db_pool(fetchval_result=1234)
    bot.db_pool = db_pool

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


@pytest.mark.asyncio
async def test_reaction_handler_self_reaction_ignored():
    db_pool, conn = make_db_pool(fetchval_result=1234)
    bot = MagicMock()
    bot.cache = None
    bot.user.id = 10
    bot.db_pool = db_pool
    handler = ReactionHandler(bot)
    payload = MagicMock(user_id=10, guild_id=1, message_id=55, emoji="✅")
    await handler.on_raw_reaction_add(payload)
    conn.fetchval.assert_not_awaited()


@pytest.mark.asyncio
async def test_reaction_handler_get_reaction_role_none_returns_early():
    db_pool, conn = make_db_pool(fetchval_result=None)
    bot = MagicMock()
    bot.cache = None
    bot.settings = MagicMock(feature_minecraft_whitelist=False)
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    bot.user.id = 999
    bot.db_pool = db_pool
    bot.get_guild = MagicMock()
    handler = ReactionHandler(bot)
    payload = MagicMock(user_id=10, guild_id=1, message_id=55, emoji="✅")
    await handler.on_raw_reaction_add(payload)
    bot.get_guild.assert_not_called()


@pytest.mark.asyncio
async def test_reaction_handler_guild_none_returns_early():
    db_pool, conn = make_db_pool(fetchval_result=1234)
    bot = MagicMock()
    bot.cache = None
    bot.settings = MagicMock(feature_minecraft_whitelist=False)
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    bot.user.id = 999
    bot.db_pool = db_pool
    bot.get_guild = MagicMock(return_value=None)
    handler = ReactionHandler(bot)
    payload = MagicMock(user_id=10, guild_id=1, message_id=55, emoji="✅")
    await handler.on_raw_reaction_add(payload)
    conn.fetchval.assert_awaited()


@pytest.mark.asyncio
async def test_reaction_handler_add_roles_http_exception_logged():
    db_pool, conn = make_db_pool(fetchval_result=1234)
    bot = MagicMock()
    bot.cache = None
    bot.settings = MagicMock(feature_minecraft_whitelist=False)
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    bot.user.id = 999
    bot.metrics = MagicMock()
    bot.metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.db_pool = db_pool
    role = MagicMock()
    member = MagicMock()
    member.add_roles = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
    guild = MagicMock()
    guild.get_member.return_value = member
    guild.get_role.return_value = role
    bot.get_guild = MagicMock(return_value=guild)
    handler = ReactionHandler(bot)
    payload = MagicMock(user_id=10, guild_id=1, message_id=55, emoji="✅")
    await handler.on_raw_reaction_add(payload)
    bot.metrics.errors_total.labels.assert_called_with(error_type="role_assignment")


@pytest.mark.asyncio
async def test_reaction_handler_remove_roles_http_exception_logged():
    db_pool, conn = make_db_pool(fetchval_result=1234)
    bot = MagicMock()
    bot.cache = None
    bot.user.id = 999
    bot.metrics = MagicMock()
    bot.metrics.errors_total.labels.return_value.inc = MagicMock()
    bot.db_pool = db_pool
    role = MagicMock()
    member = MagicMock()
    member.remove_roles = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
    guild = MagicMock()
    guild.get_member.return_value = member
    guild.get_role.return_value = role
    bot.get_guild = MagicMock(return_value=guild)
    handler = ReactionHandler(bot)
    payload = MagicMock(user_id=10, guild_id=1, message_id=55, emoji="✅")
    await handler.on_raw_reaction_remove(payload)
    bot.metrics.errors_total.labels.assert_called_with(error_type="role_removal")


@pytest.mark.asyncio
async def test_reaction_handler_remove_assigns_role():
    db_pool, conn = make_db_pool(fetchval_result=1234)
    bot = MagicMock()
    bot.cache = None
    bot.user.id = 999
    bot.db_pool = db_pool
    role = MagicMock()
    member = MagicMock()
    member.remove_roles = AsyncMock()
    guild = MagicMock()
    guild.get_member.return_value = member
    guild.get_role.return_value = role
    bot.get_guild = MagicMock(return_value=guild)
    handler = ReactionHandler(bot)
    payload = MagicMock(user_id=10, guild_id=1, message_id=55, emoji="✅")
    await handler.on_raw_reaction_remove(payload)
    member.remove_roles.assert_awaited()


@pytest.mark.asyncio
async def test_message_handler_check_user_opt_out_error_continues_processing():
    pool, conn = make_db_pool(fetchval_result=None)
    conn.fetchval = AsyncMock(side_effect=Exception("DB"))
    bot = _bot_with_metrics()
    bot.db_pool = pool
    bot.phrase_matcher = MagicMock(match_phrases=AsyncMock(return_value=[]))
    bot.media_downloader = None
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


@pytest.mark.asyncio
async def test_message_handler_phrase_match_log_failure_still_reacts(caplog):
    db_pool, conn = make_db_pool()
    conn.execute = AsyncMock(side_effect=Exception("DB down"))
    bot = MagicMock()
    bot.is_shutting_down.return_value = False
    bot.metrics = MagicMock()
    bot.metrics.messages_processed.labels.return_value.inc = MagicMock()
    bot.metrics.phrase_matches.labels.return_value.inc = MagicMock()
    bot.phrase_matcher.match_phrases = AsyncMock(return_value=[("id-1", "✅")])
    bot.db_pool = db_pool
    bot.media_downloader = None
    bot.voice_transcriber = None
    handler = MessageHandler(bot)
    message = MagicMock()
    message.author.bot = False
    message.author.id = 42
    message.id = 100
    message.content = "test"
    message.guild.id = 1
    message.channel.id = 2
    message.attachments = []
    message.add_reaction = AsyncMock()
    await handler.on_message(message)
    message.add_reaction.assert_awaited_once()
    assert "Failed to log phrase match" in caplog.text


@pytest.mark.asyncio
async def test_message_handler_phrase_match_http_exception_logged(caplog):
    bot = MagicMock()
    bot.is_shutting_down.return_value = False
    bot.metrics = MagicMock()
    bot.metrics.messages_processed.labels.return_value.inc = MagicMock()
    bot.phrase_matcher.match_phrases = AsyncMock(return_value=[("id-1", "✅")])
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    bot.media_downloader = None
    bot.voice_transcriber = None
    handler = MessageHandler(bot)
    message = MagicMock()
    message.author.bot = False
    message.author.id = 42
    message.id = 100
    message.content = "test"
    message.guild.id = 1
    message.channel.id = 2
    message.attachments = []
    message.add_reaction = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
    await handler.on_message(message)
    assert "Failed to add reaction" in caplog.text or "HTTPException" in caplog.text
