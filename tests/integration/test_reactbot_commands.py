from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

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
    bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.phrase_matcher.validate_pattern = AsyncMock()
    bot.phrase_matcher.invalidate_cache = MagicMock()
    metrics = MagicMock()
    metrics.commands_executed.labels.return_value.inc = MagicMock()
    bot.metrics = metrics
    return bot


@pytest.mark.asyncio
async def test_reactbot_add_success():
    bot = make_bot()
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()
    await commands.reactbot_add.callback(commands, interaction, phrase=r"hello", emoji="👋")
    assert conn.execute.await_count == 1
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_add_rate_limited():
    bot = make_bot()
    bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "slow down"))
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()
    await commands.reactbot_add.callback(commands, interaction, phrase=r"hello", emoji="👋")
    conn.execute.assert_not_awaited()
    interaction.followup.send.assert_awaited_with("slow down", ephemeral=True)


@pytest.mark.asyncio
async def test_reactbot_list_no_rows():
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
    bot = make_bot()
    db_pool, conn = make_db_pool(execute_result="UPDATE 0")
    bot.db_pool = db_pool
    commands = ReactBotCommands(bot)
    interaction = make_interaction()
    await commands.reactbot_remove.callback(commands, interaction, phrase="missing")
    conn.execute.assert_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_validate_emoji_accessible_custom_emoji_not_found():
    bot = make_bot()
    bot.get_emoji = MagicMock(return_value=None)
    commands = ReactBotCommands(bot)
    interaction = make_interaction()
    ok, msg = await commands._validate_emoji_accessible(interaction, "<:custom:123456789>")
    assert ok is False
    assert "Cannot access" in msg or "must be in the server" in msg


@pytest.mark.asyncio
async def test_validate_emoji_accessible_unicode_returns_true():
    bot = make_bot()
    commands = ReactBotCommands(bot)
    interaction = make_interaction()
    ok, _ = await commands._validate_emoji_accessible(interaction, "👍")
    assert ok is True


@pytest.mark.asyncio
async def test_phrase_autocomplete_empty():
    from bot.commands.reactbot import _reactbot_phrase_autocomplete

    bot = make_bot()
    db_pool, conn = make_db_pool(fetch_result=[])
    bot.db_pool = db_pool
    interaction = make_interaction()
    interaction.client = bot
    choices = await _reactbot_phrase_autocomplete(interaction, "")
    assert choices == []


@pytest.mark.asyncio
async def test_reactbot_add_validation_error():
    from bot.utils.validation import ValidationError

    bot = make_bot()
    db_pool, conn = make_db_pool()
    bot.db_pool = db_pool
    with patch(
        "bot.commands.reactbot.InputValidator.validate_phrase_pattern",
        side_effect=ValidationError("Invalid"),
    ):
        commands = ReactBotCommands(bot)
        interaction = make_interaction()
        await commands.reactbot_add.callback(commands, interaction, phrase="[invalid", emoji="👍")
    assert "❌" in str(interaction.followup.send.call_args)
