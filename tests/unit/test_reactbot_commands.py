from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from discord import app_commands

from bot.commands import reactbot as reactbot_mod
from bot.commands.reactbot import (
    ReactBotCommands,
    _add_reactbot_phrase,
    _fetch_reactbot_phrases,
    _invalidate_reactbot_cache,
    _list_reactbot_phrases,
    _reactbot_phrase_autocomplete,
    _reactbot_phrases_to_choices,
    _remove_reactbot_phrase,
)
from bot.utils.regex_validator import RegexValidationError
from bot.utils.validation import ValidationError
from tests.helpers import mock_db_ctx, mock_db_pool


def test_invalidate_cache_skips_when_none():
    _invalidate_reactbot_cache(None, 1)


def test_invalidate_cache_deletes():
    c = MagicMock()
    _invalidate_reactbot_cache(c, 42)
    c.delete.assert_called()


@pytest.mark.asyncio
async def test_fetch_reactbot_phrases():
    pool, conn = mock_db_pool(fetch=[{"phrase": "a", "emoji": "👍"}])
    rows = await _fetch_reactbot_phrases(pool, 1)
    assert rows == conn.fetch.return_value


@pytest.mark.asyncio
async def test_phrase_autocomplete_delegates(monkeypatch):
    async def fake(*a, **k):
        return []

    monkeypatch.setattr(reactbot_mod, "cached_autocomplete", fake)
    i = MagicMock()
    await _reactbot_phrase_autocomplete(i, "x")


@pytest.mark.asyncio
async def test_list_empty_rows_after_fetch():
    cog = MagicMock()
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = None
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = MagicMock(guild_id=1)
    i.followup.send = AsyncMock()
    with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
        await _list_reactbot_phrases(cog, i)
    se.assert_awaited()


def test_phrases_to_choices_long_label():
    rows = [{"phrase": "x" * 80, "emoji": "👍"}]
    choices = _reactbot_phrases_to_choices(rows, "")
    assert choices and len(choices[0].name) <= 100


@pytest.mark.asyncio
async def test_list_from_cache_hit():
    cog = MagicMock()
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = [{"phrase": "hi", "emoji": "👋", "match_count": 2}]
    cog.bot.db_pool = MagicMock()
    i = MagicMock()
    i.guild_id = 1
    i.followup.send = AsyncMock()
    await _list_reactbot_phrases(cog, i)
    cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_list_exception():
    cog = MagicMock()
    cog.bot.cache = None
    cog.bot.db_pool.acquire = MagicMock(side_effect=RuntimeError("db"))
    i = MagicMock(guild_id=1)
    i.followup.send = AsyncMock()
    with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
        await _list_reactbot_phrases(cog, i)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_add_missing_phrase_or_emoji():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    i = MagicMock()
    i.followup.send = AsyncMock()
    await _add_reactbot_phrase(cog, i, None, "👍")
    assert i.followup.send.called


@pytest.mark.asyncio
async def test_add_unique_violation():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=asyncpg.UniqueViolationError("dup"))
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    cog.bot.phrase_matcher.validate_pattern = AsyncMock()
    cog.bot.metrics = None
    i = MagicMock(guild_id=1, user=MagicMock(id=9))
    i.followup.send = AsyncMock()
    with patch("bot.commands.reactbot.InputValidator.validate_phrase_pattern", return_value="x"):
        with patch("bot.commands.reactbot.InputValidator.validate_emoji", return_value="👍"):
            with patch.object(
                cog, "_validate_emoji_accessible", AsyncMock(return_value=(True, ""))
            ):
                await _add_reactbot_phrase(cog, i, r"hello", "👍")
    assert i.followup.send.called


@pytest.mark.asyncio
async def test_add_metrics_increment():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    conn = MagicMock()
    conn.execute = AsyncMock()
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    cog.bot.phrase_matcher.validate_pattern = AsyncMock()
    labels = MagicMock()
    labels.inc = MagicMock()
    cog.bot.metrics = MagicMock()
    cog.bot.metrics.commands_executed.labels.return_value = labels
    i = MagicMock(guild_id=1, user=MagicMock(id=9))
    i.followup.send = AsyncMock()
    with patch("bot.commands.reactbot.InputValidator.validate_phrase_pattern", return_value="x"):
        with patch("bot.commands.reactbot.InputValidator.validate_emoji", return_value="👍"):
            with patch.object(
                cog, "_validate_emoji_accessible", AsyncMock(return_value=(True, ""))
            ):
                await _add_reactbot_phrase(cog, i, r"a", "👍")
    labels.inc.assert_called()


@pytest.mark.asyncio
async def test_add_generic_exception():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("x"))
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    cog.bot.phrase_matcher.validate_pattern = AsyncMock()
    i = MagicMock(guild_id=1, user=MagicMock(id=3))
    with patch("bot.commands.reactbot.InputValidator.validate_phrase_pattern", return_value="x"):
        with patch("bot.commands.reactbot.InputValidator.validate_emoji", return_value="👍"):
            with patch.object(
                cog, "_validate_emoji_accessible", AsyncMock(return_value=(True, ""))
            ):
                with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
                    await _add_reactbot_phrase(cog, i, r"x", "👍")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_remove_exception():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog.bot.db_pool.acquire = MagicMock(side_effect=RuntimeError("db"))
    i = MagicMock(guild_id=1)
    with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
        await _remove_reactbot_phrase(cog, i, "hi")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_validate_emoji_opener_without_closing_bracket():
    cog = ReactBotCommands(MagicMock())
    ok, err = await cog._validate_emoji_accessible(MagicMock(), "<:name:123456789012345678")
    assert ok is True and err == ""


@pytest.mark.asyncio
async def test_validate_emoji_custom_not_found():
    cog = ReactBotCommands(MagicMock())
    cog.bot.get_emoji = MagicMock(return_value=None)
    ok, msg = await cog._validate_emoji_accessible(MagicMock(), "<:a:123456789012345678>")
    assert ok is False


@pytest.mark.asyncio
async def test_validate_emoji_not_usable():
    cog = ReactBotCommands(MagicMock())
    em = MagicMock()
    em.is_usable.return_value = False
    cog.bot.get_emoji = MagicMock(return_value=em)
    ok, _ = await cog._validate_emoji_accessible(MagicMock(), "<:x:123456789012345678>")
    assert ok is False


@pytest.mark.asyncio
async def test_validate_custom_emoji_found_and_usable():
    cog = ReactBotCommands(MagicMock())
    em = MagicMock()
    em.is_usable.return_value = True
    cog.bot.get_emoji = MagicMock(return_value=em)
    ok, msg = await cog._validate_emoji_accessible(MagicMock(), "<:ok:123456789012345678>")
    assert ok is True and msg == ""


@pytest.mark.asyncio
async def test_add_rejects_inaccessible_custom_emoji():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog.bot.get_emoji = MagicMock(return_value=None)
    cog.bot.phrase_matcher.validate_pattern = AsyncMock()
    cog.bot.db_pool = MagicMock()
    i = MagicMock(guild_id=1, user=MagicMock(id=9))
    i.followup.send = AsyncMock()
    custom = "<:missing:123456789012345678>"
    with patch("bot.commands.reactbot.InputValidator.validate_phrase_pattern", return_value="hi"):
        with patch("bot.commands.reactbot.InputValidator.validate_emoji", return_value=custom):
            with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
                await _add_reactbot_phrase(cog, i, r"hi", custom)
    se.assert_awaited()
    cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_validate_emoji_invalid_parts_pass_through():
    cog = ReactBotCommands(MagicMock())
    ok, err = await cog._validate_emoji_accessible(MagicMock(), "<:a:notint>")
    assert ok is True and err == ""


@pytest.mark.asyncio
async def test_validate_emoji_custom_tag_fewer_than_three_parts_ok():
    cog = ReactBotCommands(MagicMock())
    ok, err = await cog._validate_emoji_accessible(MagicMock(), "<x:y>")
    assert ok is True and err == ""


@pytest.mark.asyncio
async def test_validate_emoji_bracket_opener_only_short_circuits():
    cog = ReactBotCommands(MagicMock())
    ok, err = await cog._validate_emoji_accessible(MagicMock(), "<not_closed_token")
    assert ok is True and err == ""


def test_phrases_to_choices_skips_non_matching_current():
    rows = [{"phrase": "alpha", "emoji": "👍"}]
    assert _reactbot_phrases_to_choices(rows, "nomatch") == []


def test_phrases_to_choices_truncates_very_long_display():
    rows = [{"phrase": "p" * 200, "emoji": "👍"}]
    choices = _reactbot_phrases_to_choices(rows, "p")
    assert choices and choices[0].name.endswith("...")


@pytest.mark.asyncio
async def test_list_populates_cache_from_db():
    cog = MagicMock()
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = None
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[{"phrase": "a", "emoji": "👍", "match_count": 0}])
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = MagicMock(guild_id=1)
    i.followup.send = AsyncMock()
    await _list_reactbot_phrases(cog, i)
    cog.bot.cache.set.assert_called()


@pytest.mark.asyncio
async def test_remove_not_found_send_error():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="UPDATE 0")
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = MagicMock(guild_id=1)
    with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
        await _remove_reactbot_phrase(cog, i, "nope")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_list_db_fetch_without_bot_cache():
    cog = MagicMock()
    cog.bot.cache = None
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[{"phrase": "a", "emoji": "👍", "match_count": 0}])
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = MagicMock(guild_id=1)
    i.followup.send = AsyncMock()
    await _list_reactbot_phrases(cog, i)


@pytest.mark.asyncio
async def test_validate_emoji_custom_id_valueerror_passes():
    cog = ReactBotCommands(MagicMock())
    ok, err = await cog._validate_emoji_accessible(MagicMock(), "<:e:name:notint>")
    assert ok is True and err == ""


@pytest.mark.asyncio
async def test_add_require_admin_false():
    cog = ReactBotCommands(MagicMock())
    cog.bot.db_pool = MagicMock()
    with patch("bot.commands.reactbot.require_admin", AsyncMock(return_value=False)):
        i = MagicMock()
        await _add_reactbot_phrase(cog, i, "x", "👍")
    cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_add_emoji_not_accessible():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    i = MagicMock(guild_id=1)
    with patch("bot.commands.reactbot.InputValidator.validate_phrase_pattern", return_value="a"):
        with patch("bot.commands.reactbot.InputValidator.validate_emoji", return_value="👍"):
            with patch.object(
                cog, "_validate_emoji_accessible", AsyncMock(return_value=(False, "bad"))
            ):
                with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
                    await _add_reactbot_phrase(cog, i, "a", "👍")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_add_success_without_metrics():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog.bot.metrics = None
    conn = MagicMock()
    conn.execute = AsyncMock()
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    cog.bot.phrase_matcher.validate_pattern = AsyncMock()
    i = MagicMock(guild_id=1, user=MagicMock(id=3))
    i.followup.send = AsyncMock()
    with patch("bot.commands.reactbot.InputValidator.validate_phrase_pattern", return_value="a"):
        with patch("bot.commands.reactbot.InputValidator.validate_emoji", return_value="👍"):
            with patch.object(
                cog, "_validate_emoji_accessible", AsyncMock(return_value=(True, ""))
            ):
                await _add_reactbot_phrase(cog, i, r"a", "👍")
    assert i.followup.send.called


@pytest.mark.asyncio
async def test_remove_missing_phrase():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    i = MagicMock(followup=MagicMock(send=AsyncMock()))
    await _remove_reactbot_phrase(cog, i, None)


@pytest.mark.asyncio
async def test_remove_require_admin_false():
    cog = ReactBotCommands(MagicMock())
    cog.bot.db_pool = MagicMock()
    with patch("bot.commands.reactbot.require_admin", AsyncMock(return_value=False)):
        i = MagicMock()
        await _remove_reactbot_phrase(cog, i, "x")
    cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_add_validation_error_from_phrase():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    i = MagicMock(guild_id=1)
    with patch(
        "bot.commands.reactbot.InputValidator.validate_phrase_pattern",
        side_effect=ValidationError("bad"),
    ):
        with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
            await _add_reactbot_phrase(cog, i, "x", "👍")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_add_regex_error_from_matcher():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    cog.bot.phrase_matcher.validate_pattern = AsyncMock(side_effect=RegexValidationError("rx"))
    i = MagicMock(guild_id=1)
    with patch("bot.commands.reactbot.InputValidator.validate_phrase_pattern", return_value="a"):
        with patch("bot.commands.reactbot.InputValidator.validate_emoji", return_value="👍"):
            with patch.object(
                cog, "_validate_emoji_accessible", AsyncMock(return_value=(True, ""))
            ):
                with patch("bot.commands.reactbot.send_error", new_callable=AsyncMock) as se:
                    await _add_reactbot_phrase(cog, i, "a", "👍")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_remove_success_followup():
    cog = ReactBotCommands(MagicMock())
    cog.bot.permission_checker.check_role = AsyncMock(return_value=True)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    cog.bot.db_pool = MagicMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    cog.bot.phrase_matcher.invalidate_cache = MagicMock()
    i = MagicMock(guild_id=1, followup=MagicMock(send=AsyncMock()))
    await _remove_reactbot_phrase(cog, i, "hi")
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_validate_emoji_custom_usable():
    cog = ReactBotCommands(MagicMock())
    em = MagicMock()
    em.is_usable.return_value = True
    cog.bot.get_emoji = MagicMock(return_value=em)
    ok, err = await cog._validate_emoji_accessible(MagicMock(), "<:x:123456789012345678>")
    assert ok is True and err == ""


@pytest.mark.asyncio
async def test_reactbot_cmd_invokes_list_handler():
    bot = MagicMock()
    cog = ReactBotCommands(bot)
    i = MagicMock()
    i.response.defer = AsyncMock()
    i.guild_id = 1
    i.followup.send = AsyncMock()
    bot.cache = MagicMock()
    bot.cache.get.return_value = [{"phrase": "a", "emoji": "👍", "match_count": 0}]
    op = app_commands.Choice(name="List", value="list")
    await cog.reactbot_cmd.callback(i, op)


@pytest.mark.asyncio
async def test_reactbot_cmd_unknown_operation():
    bot = MagicMock()
    cog = ReactBotCommands(bot)
    i = MagicMock()
    i.response.defer = AsyncMock()
    bad = app_commands.Choice(name="Bad", value="nope")
    await cog.reactbot_cmd.callback(i, bad)


@pytest.mark.asyncio
async def test_cog_load_unload_setup():
    bot = MagicMock()
    bot.tree.add_command = MagicMock()
    cog = ReactBotCommands(bot)
    await cog.cog_load()
    bot.tree.remove_command = MagicMock()
    await cog.cog_unload()

    from bot.commands import reactbot as rb

    bot.add_cog = AsyncMock()
    await rb.setup(bot)
    bot.add_cog.assert_awaited_once()
