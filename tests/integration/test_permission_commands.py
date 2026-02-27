"""Tests for PermissionCommands cog."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.permissions import PermissionCommands


def make_interaction():
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user.id = 10
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_user(user_id: int, name: str = "user"):
    user = MagicMock()
    user.id = user_id
    user.name = name
    user.mention = f"<@{user_id}>"
    return user


def make_db_pool(fetch_rows=None, execute_result="OK"):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=execute_result)
    conn.fetch = AsyncMock(return_value=fetch_rows or [])

    @asynccontextmanager
    async def acquire():
        yield conn

    db_pool = MagicMock()
    db_pool.acquire = acquire
    return db_pool, conn


def make_bot(fetch_rows=None, execute_result="OK"):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.permission_checker.invalidate_user_cache = MagicMock()

    db_pool, conn = make_db_pool(fetch_rows, execute_result)
    bot.db_pool = db_pool

    async def fetch_user(user_id: int):
        return make_user(user_id, f"user-{user_id}")

    bot.fetch_user = fetch_user

    return bot, conn


@pytest.mark.asyncio
async def test_grant_role_happy_path():
    """grant_role inserts permission and writes audit log when authorized."""
    bot, conn = make_bot()
    cog = PermissionCommands(bot)
    interaction = make_interaction()
    target_user = make_user(20, "target")

    await cog.grant_role.callback(cog, interaction, user=target_user, role="admin")

    # Two execute calls: insert user_permissions + audit_log
    assert conn.execute.await_count == 2
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(
        interaction.guild_id, target_user.id
    )
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_grant_role_permission_denied():
    """grant_role returns early if caller is not super admin."""
    bot, conn = make_bot()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    cog = PermissionCommands(bot)
    interaction = make_interaction()
    target_user = make_user(20)

    await cog.grant_role.callback(cog, interaction, user=target_user, role="admin")

    conn.execute.assert_not_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_success():
    """revoke_role marks permission inactive and writes audit log."""
    bot, conn = make_bot(execute_result="UPDATE 1")
    cog = PermissionCommands(bot)
    interaction = make_interaction()
    target_user = make_user(20)

    await cog.revoke_role.callback(cog, interaction, user=target_user, role="admin")

    assert conn.execute.await_count == 2
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(
        interaction.guild_id, target_user.id
    )
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_not_found():
    """revoke_role reports when no active role exists."""
    bot, conn = make_bot(execute_result="UPDATE 0")
    cog = PermissionCommands(bot)
    interaction = make_interaction()
    target_user = make_user(20)

    await cog.revoke_role.callback(cog, interaction, user=target_user, role="admin")

    conn.execute.assert_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_list_permissions_with_rows():
    """list_permissions formats a response when rows exist."""
    rows = [
        {"user_id": 20, "role": "super_admin", "granted_at": None},
        {"user_id": 21, "role": "admin", "granted_at": None},
    ]
    bot, conn = make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    interaction = make_interaction()

    await cog.list_permissions.callback(cog, interaction)

    conn.fetch.assert_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_list_permissions_empty():
    """list_permissions handles empty result set."""
    bot, conn = make_bot(fetch_rows=[])
    cog = PermissionCommands(bot)
    interaction = make_interaction()

    await cog.list_permissions.callback(cog, interaction)

    conn.fetch.assert_awaited()
    interaction.followup.send.assert_awaited()

