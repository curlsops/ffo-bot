from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.permissions import PermissionCommands


def make_interaction():
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user.id = 10
    guild = MagicMock()
    guild.get_member = MagicMock(return_value=None)
    interaction.guild = guild
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_user(user_id: int, name: str = "user"):
    user = MagicMock()
    user.id = user_id
    user.name = name
    user.mention = f"<@{user_id}>"
    return user


def make_db_pool(fetch_rows=None, fetchrow_result=None, fetchval_result=None, execute_result="OK"):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=execute_result)
    conn.fetch = AsyncMock(return_value=fetch_rows or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_result or {"config": {}})
    conn.fetchval = AsyncMock(return_value=fetchval_result)

    @asynccontextmanager
    async def acquire():
        yield conn

    db_pool = MagicMock()
    db_pool.acquire = acquire
    return db_pool, conn


def make_bot(fetch_rows=None, fetchrow_result=None, fetchval_result=None, execute_result="OK"):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.permission_checker.invalidate_user_cache = MagicMock()
    bot._register_server = AsyncMock()
    bot.cache = MagicMock()
    bot.cache.get = MagicMock(return_value=None)
    db_pool, conn = make_db_pool(fetch_rows, fetchrow_result, fetchval_result, execute_result)
    bot.db_pool = db_pool
    bot.fetch_user = AsyncMock(side_effect=lambda uid: make_user(uid, f"user-{uid}"))
    return bot, conn


def get_add_cmd(cog):
    return cog.permissions_group.get_command("add")


def get_remove_cmd(cog):
    return cog.permissions_group.get_command("remove")


def get_list_cmd(cog):
    return cog.permissions_group.get_command("list")


@pytest.mark.asyncio
async def test_grant_role_happy_path():
    bot, conn = make_bot(fetchval_result=None)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    target_user = make_user(20, "target")
    await get_add_cmd(cog).callback(permissions_group, interaction, user=str(target_user.id), role="admin")
    conn.fetchval.assert_awaited_once()
    assert conn.execute.await_count == 1
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(
        interaction.guild_id, target_user.id
    )
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_grant_role_already_has_role():
    bot, conn = make_bot(fetchval_result=1)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    target_user = make_user(20, "target")
    await get_add_cmd(cog).callback(permissions_group, interaction, user=str(target_user.id), role="admin")
    conn.fetchval.assert_awaited_once()
    conn.execute.assert_not_awaited()
    assert "already has" in str(interaction.followup.send.call_args).lower()


@pytest.mark.asyncio
async def test_grant_role_permission_denied():
    bot, conn = make_bot(fetchval_result=None)
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    target_user = make_user(20)
    await get_add_cmd(cog).callback(permissions_group, interaction, user=str(target_user.id), role="admin")
    conn.execute.assert_not_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_success():
    bot, conn = make_bot(execute_result="UPDATE 1")
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    target_user = make_user(20)
    await get_remove_cmd(cog).callback(permissions_group, interaction, user=str(target_user.id), role="admin")
    assert conn.execute.await_count == 1
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(
        interaction.guild_id, target_user.id
    )
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_not_found():
    bot, conn = make_bot(execute_result="UPDATE 0")
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    target_user = make_user(20)
    await get_remove_cmd(cog).callback(permissions_group, interaction, user=str(target_user.id), role="admin")
    conn.execute.assert_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_list_permissions_with_rows():
    rows = [
        {"user_id": 20, "role": "super_admin", "granted_at": None},
        {"user_id": 21, "role": "admin", "granted_at": None},
    ]
    bot, conn = make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    await get_list_cmd(cog).callback(permissions_group, interaction)
    conn.fetch.assert_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_list_permissions_empty():
    bot, conn = make_bot(fetch_rows=[])
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    await get_list_cmd(cog).callback(permissions_group, interaction)
    conn.fetch.assert_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_grant_role_db_error():
    bot, conn = make_bot(fetchval_result=None)
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(side_effect=Exception("DB error"))
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    target_user = make_user(20)
    await get_add_cmd(cog).callback(permissions_group, interaction, user=str(target_user.id), role="admin")
    assert "Error granting" in str(interaction.followup.send.call_args)


@pytest.mark.asyncio
async def test_revoke_role_db_error():
    bot, conn = make_bot()
    conn.execute = AsyncMock(side_effect=Exception("DB error"))
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    target_user = make_user(20)
    await get_remove_cmd(cog).callback(permissions_group, interaction, user=str(target_user.id), role="admin")
    assert "Error revoking" in str(interaction.followup.send.call_args)


@pytest.mark.asyncio
async def test_list_permissions_paginated():
    rows = [{"user_id": i, "role": "moderator"} for i in range(15)]
    bot, conn = make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    await get_list_cmd(cog).callback(permissions_group, interaction)
    call = interaction.followup.send.call_args
    msg = call[0][0]
    view = call[1]["view"]
    assert "User permissions" in msg
    assert "1/2" in str(view.page_btn.label)
    assert view.mode == "user"


@pytest.mark.asyncio
async def test_list_permissions_unknown_role_emoji():
    rows = [{"user_id": 1, "role": "unknown_role"}]
    bot, conn = make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    await get_list_cmd(cog).callback(permissions_group, interaction)
    msg = interaction.followup.send.call_args[0][0]
    assert "Unknown" in msg or "unknown_role" in msg
