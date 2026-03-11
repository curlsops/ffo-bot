from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.reactbot import ReactBotCommands
from tests.helpers import assert_followup_contains, invoke, mock_db_pool, mock_interaction


def _make_bot():
    bot = MagicMock()
    bot.cache = None
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
    bot = _make_bot()
    db_pool, conn = mock_db_pool()
    bot.db_pool = db_pool
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    await invoke(cog, "reactbot_group", "add_cmd", i, phrase=r"hello", emoji="👋")
    assert conn.execute.await_count == 1
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_add_rate_limited():
    bot = _make_bot()
    bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
    db_pool, conn = mock_db_pool()
    bot.db_pool = db_pool
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    await invoke(cog, "reactbot_group", "add_cmd", i, phrase=r"hello", emoji="👋")
    conn.execute.assert_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_list_no_rows():
    bot = _make_bot()
    db_pool, conn = mock_db_pool(fetch=[])
    bot.db_pool = db_pool
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    await invoke(cog, "reactbot_group", "list_cmd", i)
    conn.fetch.assert_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_list_with_rows():
    rows = [
        {"phrase": "hello", "emoji": "👋", "match_count": 5, "last_matched_at": None},
        {"phrase": "test", "emoji": "✅", "match_count": 1, "last_matched_at": None},
    ]
    bot = _make_bot()
    db_pool, _ = mock_db_pool(fetch=rows)
    bot.db_pool = db_pool
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    await invoke(cog, "reactbot_group", "list_cmd", i)
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_remove_success():
    bot = _make_bot()
    db_pool, conn = mock_db_pool(execute="UPDATE 1")
    bot.db_pool = db_pool
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    await invoke(cog, "reactbot_group", "remove_cmd", i, phrase="hello")
    conn.execute.assert_awaited()
    bot.phrase_matcher.invalidate_cache.assert_called_once_with(i.guild_id)
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_remove_not_found():
    bot = _make_bot()
    db_pool, conn = mock_db_pool(execute="UPDATE 0")
    bot.db_pool = db_pool
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    await invoke(cog, "reactbot_group", "remove_cmd", i, phrase="missing")
    conn.execute.assert_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_validate_emoji_accessible_custom_emoji_not_found():
    bot = _make_bot()
    bot.get_emoji = MagicMock(return_value=None)
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    ok, msg = await cog._validate_emoji_accessible(i, "<:custom:123456789>")
    assert ok is False
    assert "Cannot access" in msg or "must be in the server" in msg


@pytest.mark.asyncio
async def test_validate_emoji_accessible_unicode_returns_true():
    bot = _make_bot()
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    ok, _ = await cog._validate_emoji_accessible(i, "👍")
    assert ok is True


@pytest.mark.asyncio
async def test_phrase_autocomplete_empty():
    from bot.commands.reactbot import _reactbot_phrase_autocomplete

    bot = _make_bot()
    db_pool, conn = mock_db_pool(fetch=[])
    bot.db_pool = db_pool
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    i.client = bot
    choices = await _reactbot_phrase_autocomplete(i, "")
    assert choices == []


@pytest.mark.parametrize("phrase,emoji", [("hello", "👋"), ("test", "✅"), ("foo", "👍")])
@pytest.mark.asyncio
async def test_reactbot_add_various_phrases(phrase, emoji):
    bot = _make_bot()
    db_pool, conn = mock_db_pool()
    bot.db_pool = db_pool
    cog = ReactBotCommands(bot)
    i = mock_interaction(guild_id=123456789, user_id=987654321)
    await invoke(cog, "reactbot_group", "add_cmd", i, phrase=phrase, emoji=emoji)
    conn.execute.assert_awaited_once()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_reactbot_add_validation_error():
    from bot.utils.validation import ValidationError

    bot = _make_bot()
    db_pool, conn = mock_db_pool()
    bot.db_pool = db_pool
    with patch(
        "bot.commands.reactbot.InputValidator.validate_phrase_pattern",
        side_effect=ValidationError("Invalid"),
    ):
        cog = ReactBotCommands(bot)
        i = mock_interaction(guild_id=123456789, user_id=987654321)
        await invoke(cog, "reactbot_group", "add_cmd", i, phrase="[invalid", emoji="👍")
    assert_followup_contains(i, "❌")
