from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

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
    db_pool, _ = make_db_pool(fetchval_result=None)
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
    db_pool, _ = make_db_pool(fetchval_result=1234)
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
    db_pool, _ = make_db_pool(fetchval_result=1234)
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
    db_pool, _ = make_db_pool(fetchval_result=1234)
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
