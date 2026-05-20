from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord import app_commands

from bot.commands.privacy import PrivacyCommands


@asynccontextmanager
async def _pool(conn):
    yield conn


def _interaction():
    interaction = MagicMock()
    interaction.guild_id = 111
    interaction.user.id = 222
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _choice(value: str) -> app_commands.Choice[str]:
    return app_commands.Choice(name=value, value=value)


@pytest.mark.asyncio
async def test_privacy_optout_executes_expected_queries():
    bot = MagicMock()
    bot.cache = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    bot.db_pool.acquire = lambda: _pool(conn)
    interaction = _interaction()

    with patch("bot.commands.privacy.invalidate_opt_out_cache") as invalidate:
        cog = PrivacyCommands(bot)
        await cog.privacy_cmd.callback(interaction, operation=_choice("optout"))

    assert conn.execute.await_count == 2
    assert "user_preferences" in conn.execute.await_args_list[0].args[0]
    assert "message_metadata" in conn.execute.await_args_list[1].args[0]
    invalidate.assert_called_once_with(bot.cache, 111, 222)
    interaction.followup.send.assert_awaited_once_with(
        "✅ Opted out. Your message history has been deleted.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_privacy_optin_updates_preference_and_confirms():
    bot = MagicMock()
    bot.cache = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    bot.db_pool.acquire = lambda: _pool(conn)
    interaction = _interaction()

    with patch("bot.commands.privacy.invalidate_opt_out_cache") as invalidate:
        cog = PrivacyCommands(bot)
        await cog.privacy_cmd.callback(interaction, operation=_choice("optin"))

    conn.execute.assert_awaited_once()
    assert "user_preferences" in conn.execute.await_args.args[0]
    invalidate.assert_called_once_with(bot.cache, 111, 222)
    interaction.followup.send.assert_awaited_once_with(
        "✅ Opted back in to message tracking.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_privacy_db_error_sends_error_message():
    bot = MagicMock()
    bot.cache = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=Exception("DB"))
    bot.db_pool.acquire = lambda: _pool(conn)
    interaction = _interaction()

    cog = PrivacyCommands(bot)
    await cog.privacy_cmd.callback(interaction, operation=_choice("optout"))

    interaction.followup.send.assert_awaited_once_with("❌ An error occurred.", ephemeral=True)


@pytest.mark.asyncio
async def test_privacy_cog_load_registers_command():
    bot = MagicMock()
    cog = PrivacyCommands(bot)
    await cog.cog_load()
    bot.tree.add_command.assert_called_once_with(cog.privacy_cmd)


@pytest.mark.asyncio
async def test_privacy_cog_unload_removes_command():
    bot = MagicMock()
    cog = PrivacyCommands(bot)
    await cog.cog_unload()
    bot.tree.remove_command.assert_called_once_with(cog.privacy_cmd.name)


@pytest.mark.asyncio
async def test_privacy_setup():
    bot = MagicMock()
    bot.add_cog = AsyncMock()

    from bot.commands.privacy import setup

    await setup(bot)
    bot.add_cog.assert_awaited_once()
