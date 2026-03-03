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


def make_db_pool(fetch_rows=None, fetchrow_result=None, execute_result="OK"):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=execute_result)
    conn.fetch = AsyncMock(return_value=fetch_rows or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_result or {"config": {}})

    @asynccontextmanager
    async def acquire():
        yield conn

    db_pool = MagicMock()
    db_pool.acquire = acquire
    return db_pool, conn


def make_bot(fetch_rows=None, fetchrow_result=None, execute_result="OK"):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.permission_checker.invalidate_user_cache = MagicMock()
    bot._register_server = AsyncMock()
    db_pool, conn = make_db_pool(fetch_rows, fetchrow_result, execute_result)
    bot.db_pool = db_pool
    bot.fetch_user = lambda user_id: make_user(user_id, f"user-{user_id}")
    return bot, conn


def get_role_add_cmd(cog):
    return cog.permissions_group.get_command("role").get_command("add")


def get_role_remove_cmd(cog):
    return cog.permissions_group.get_command("role").get_command("remove")


def get_list_cmd(cog):
    return cog.permissions_group.get_command("list")


@pytest.mark.asyncio
async def test_grant_role_happy_path():
    bot, conn = make_bot()
    cog = PermissionCommands(bot)
    role_group = cog.permissions_group.get_command("role")
    interaction = make_interaction()
    target_user = make_user(20, "target")
    await get_role_add_cmd(cog).callback(role_group, interaction, user=target_user, role="admin")
    assert conn.execute.await_count == 1
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(
        interaction.guild_id, target_user.id
    )
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_grant_role_permission_denied():
    bot, conn = make_bot()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    cog = PermissionCommands(bot)
    role_group = cog.permissions_group.get_command("role")
    interaction = make_interaction()
    target_user = make_user(20)
    await get_role_add_cmd(cog).callback(role_group, interaction, user=target_user, role="admin")
    conn.execute.assert_not_awaited()
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_success():
    bot, conn = make_bot(execute_result="UPDATE 1")
    cog = PermissionCommands(bot)
    role_group = cog.permissions_group.get_command("role")
    interaction = make_interaction()
    target_user = make_user(20)
    await get_role_remove_cmd(cog).callback(role_group, interaction, user=target_user, role="admin")
    assert conn.execute.await_count == 1
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(
        interaction.guild_id, target_user.id
    )
    interaction.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_not_found():
    bot, conn = make_bot(execute_result="UPDATE 0")
    cog = PermissionCommands(bot)
    role_group = cog.permissions_group.get_command("role")
    interaction = make_interaction()
    target_user = make_user(20)
    await get_role_remove_cmd(cog).callback(role_group, interaction, user=target_user, role="admin")
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
    bot, conn = make_bot()
    conn.execute = AsyncMock(side_effect=Exception("DB error"))
    cog = PermissionCommands(bot)
    role_group = cog.permissions_group.get_command("role")
    interaction = make_interaction()
    target_user = make_user(20)
    await get_role_add_cmd(cog).callback(role_group, interaction, user=target_user, role="admin")
    assert "Error granting" in str(interaction.followup.send.call_args)


@pytest.mark.asyncio
async def test_revoke_role_db_error():
    bot, conn = make_bot()
    conn.execute = AsyncMock(side_effect=Exception("DB error"))
    cog = PermissionCommands(bot)
    role_group = cog.permissions_group.get_command("role")
    interaction = make_interaction()
    target_user = make_user(20)
    await get_role_remove_cmd(cog).callback(role_group, interaction, user=target_user, role="admin")
    assert "Error revoking" in str(interaction.followup.send.call_args)


@pytest.mark.asyncio
async def test_list_permissions_truncation():
    rows = [{"user_id": i, "role": "moderator"} for i in range(30)]
    bot, conn = make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    await get_list_cmd(cog).callback(permissions_group, interaction)
    msg = interaction.followup.send.call_args[0][0]
    assert "and 5 more" in msg


@pytest.mark.asyncio
async def test_list_permissions_unknown_role_emoji():
    rows = [{"user_id": 1, "role": "unknown_role"}]
    bot, conn = make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    permissions_group = cog.permissions_group
    interaction = make_interaction()
    await get_list_cmd(cog).callback(permissions_group, interaction)
    msg = interaction.followup.send.call_args[0][0]
    assert "Unknown" in msg
