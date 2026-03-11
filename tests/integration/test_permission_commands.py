from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.permissions import PermissionCommands
from tests.helpers import assert_followup_contains, mock_db_pool, mock_interaction, mock_user


def _make_bot(fetch_rows=None, fetchrow_result=None, fetchval_result=None, execute_result="OK"):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.permission_checker.invalidate_user_cache = MagicMock()
    bot._register_server = AsyncMock()
    bot.cache = MagicMock()
    bot.cache.get = MagicMock(return_value=None)
    pool, conn = mock_db_pool(
        fetch=fetch_rows, fetchrow=fetchrow_result, fetchval=fetchval_result, execute=execute_result
    )
    bot.db_pool = pool
    bot.fetch_user = AsyncMock(side_effect=lambda uid: mock_user(uid, f"user-{uid}"))
    return bot, conn


def _get_add_cmd(cog):
    return cog.permissions_group.get_command("add")


def _get_remove_cmd(cog):
    return cog.permissions_group.get_command("remove")


def _get_list_cmd(cog):
    return cog.permissions_group.get_command("list")


@pytest.mark.asyncio
async def test_grant_role_happy_path():
    bot, conn = _make_bot(fetchval_result=None)
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    user = mock_user(20)
    await _get_add_cmd(cog).callback(cog.permissions_group, i, user=str(user.id), role="admin")
    conn.fetchval.assert_awaited_once()
    assert conn.execute.await_count == 1
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(i.guild_id, user.id)
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_grant_role_already_has_role():
    bot, conn = _make_bot(fetchval_result=1)
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_add_cmd(cog).callback(cog.permissions_group, i, user="20", role="admin")
    conn.fetchval.assert_awaited_once()
    conn.execute.assert_not_awaited()
    assert_followup_contains(i, "already has", case_sensitive=False)


@pytest.mark.asyncio
async def test_grant_role_permission_denied():
    bot, conn = _make_bot(fetchval_result=None)
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_add_cmd(cog).callback(cog.permissions_group, i, user="20", role="admin")
    conn.execute.assert_not_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_success():
    bot, conn = _make_bot(execute_result="UPDATE 1")
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_remove_cmd(cog).callback(cog.permissions_group, i, user="20", role="admin")
    assert conn.execute.await_count == 1
    bot.permission_checker.invalidate_user_cache.assert_called_once_with(i.guild_id, 20)
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_role_not_found():
    bot, conn = _make_bot(execute_result="UPDATE 0")
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_remove_cmd(cog).callback(cog.permissions_group, i, user="20", role="admin")
    conn.execute.assert_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_list_permissions_with_rows():
    rows = [
        {"user_id": 20, "role": "super_admin", "granted_at": None},
        {"user_id": 21, "role": "admin", "granted_at": None},
    ]
    bot, conn = _make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_list_cmd(cog).callback(cog.permissions_group, i)
    conn.fetch.assert_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_list_permissions_empty():
    bot, conn = _make_bot(fetch_rows=[])
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_list_cmd(cog).callback(cog.permissions_group, i)
    conn.fetch.assert_awaited()
    i.followup.send.assert_awaited()


@pytest.mark.asyncio
async def test_grant_role_db_error():
    bot, conn = _make_bot(fetchval_result=None)
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(side_effect=Exception("DB error"))
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_add_cmd(cog).callback(cog.permissions_group, i, user="20", role="admin")
    assert_followup_contains(i, "Error granting")


@pytest.mark.asyncio
async def test_revoke_role_db_error():
    bot, conn = _make_bot()
    conn.execute = AsyncMock(side_effect=Exception("DB error"))
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_remove_cmd(cog).callback(cog.permissions_group, i, user="20", role="admin")
    assert_followup_contains(i, "Error revoking")


@pytest.mark.asyncio
async def test_list_permissions_paginated():
    rows = [{"user_id": n, "role": "moderator"} for n in range(15)]
    bot, conn = _make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_list_cmd(cog).callback(cog.permissions_group, i)
    call = i.followup.send.call_args
    msg = call[0][0]
    view = call[1]["view"]
    assert "User permissions" in msg
    assert "1/2" in str(view.page_btn.label)
    assert view.mode == "user"


@pytest.mark.asyncio
async def test_list_permissions_unknown_role_emoji():
    rows = [{"user_id": 1, "role": "unknown_role"}]
    bot, conn = _make_bot(fetch_rows=rows)
    cog = PermissionCommands(bot)
    i = mock_interaction(user_id=10, guild_get_member=None)
    await _get_list_cmd(cog).callback(cog.permissions_group, i)
    msg = i.followup.send.call_args[0][0]
    assert "Unknown" in msg or "unknown_role" in msg
