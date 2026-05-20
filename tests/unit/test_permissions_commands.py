from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.permissions import (
    PermissionCommands,
    PermissionsListView,
    _make_perm_nav_buttons,
    _parse_user_and_target,
    _permissions_user_autocomplete,
    _role_members,
)
from config.constants import Role
from tests.helpers import assert_followup_contains, mock_db_pool, mock_interaction, mock_user


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.permission_checker.invalidate_user_cache = MagicMock()
    bot._register_server = AsyncMock()
    bot.cache = MagicMock()
    bot.notifier = MagicMock()
    bot.notifier.notify_permission_changed = AsyncMock()
    pool, conn = mock_db_pool()
    bot.db_pool = pool
    bot.fetch_user = AsyncMock(side_effect=lambda uid: mock_user(uid, f"u{uid}"))
    return bot


@pytest.fixture
def cog(mock_bot):
    return PermissionCommands(mock_bot)


@pytest.mark.asyncio
async def test_permissions_user_autocomplete_no_guild():
    i = MagicMock(guild=None)
    assert await _permissions_user_autocomplete(i, "") == []


@pytest.mark.asyncio
async def test_permissions_user_autocomplete_filters():
    u1 = MagicMock(bot=False, display_name="AliceTest", name="alice", id=11)
    u2 = MagicMock(bot=True, display_name="Bot", name="bot", id=22)
    guild = MagicMock()
    guild.members = [u1, u2]
    i = MagicMock(guild=guild)
    choices = await _permissions_user_autocomplete(i, "alice")
    assert any(c.value == "11" for c in choices)
    assert all(c.value != "22" for c in choices)


@pytest.mark.asyncio
async def test_parse_user_no_guild(mock_bot):
    i = MagicMock(guild=None)
    uid, target, err = await _parse_user_and_target(i, "5", mock_bot)
    assert uid is None and err == "Server only."


@pytest.mark.asyncio
async def test_parse_user_invalid(mock_bot):
    i = mock_interaction()
    uid, target, err = await _parse_user_and_target(i, "notint", mock_bot)
    assert err == "Invalid user."


@pytest.mark.asyncio
async def test_parse_user_fetch_when_not_member(mock_bot):
    guild = MagicMock()
    guild.get_member = MagicMock(return_value=None)
    i = MagicMock(guild=guild)
    i.guild = guild
    mock_bot.fetch_user = AsyncMock(return_value=mock_user(99, "remote"))
    uid, target, err = await _parse_user_and_target(i, "99", mock_bot)
    assert uid == 99 and target is not None and err is None


@pytest.mark.asyncio
async def test_parse_user_not_found(mock_bot):
    guild = MagicMock()
    guild.get_member = MagicMock(return_value=None)
    i = MagicMock(guild=guild)
    i.guild = guild
    mock_bot.fetch_user = AsyncMock(return_value=None)
    uid, target, err = await _parse_user_and_target(i, "99", mock_bot)
    assert err == "User not found."


def test_role_members_prefers_highest():
    guild = MagicMock()
    sa_role = MagicMock()
    sa_role.members = [MagicMock(id=1)]
    ad_role = MagicMock()
    ad_role.members = [MagicMock(id=1)]
    guild.get_role = MagicMock(side_effect=lambda rid: {10: sa_role, 20: ad_role}[rid])
    role_ids = {Role.SUPER_ADMIN: 10, Role.ADMIN: 20}
    pairs = _role_members(guild, role_ids)
    assert pairs[0][0] == 1
    assert pairs[0][1] == Role.SUPER_ADMIN


def test_make_perm_nav_buttons():
    view = PermissionsListView(role_ids={}, role_members=[], user_rows=[])
    btns = _make_perm_nav_buttons(view)
    assert len(btns) == 4


@pytest.mark.asyncio
async def test_permissions_list_view_toggle_and_paging():
    role_ids = {Role.ADMIN: 123}
    role_members = [(1, Role.ADMIN)]
    user_rows = [{"user_id": 9, "role": "admin"}]
    view = PermissionsListView(
        role_ids=role_ids,
        role_members=role_members,
        user_rows=user_rows,
    )
    i = MagicMock()
    i.response.edit_message = AsyncMock()
    await view._toggle_callback(i)
    assert view.mode == "user"
    view.page = 1
    await view._prev_callback(i)
    assert view.page == 0
    view._max_page = 0
    await view._next_callback(i)
    assert view.page == 0


@pytest.mark.asyncio
async def test_permissions_list_empty_message(cog, mock_bot):
    with patch(
        "bot.commands.permissions.get_server_role_ids",
        new_callable=AsyncMock,
        return_value={},
    ):
        pool, conn = mock_db_pool(fetch=[])
        mock_bot.db_pool = pool
        i = mock_interaction()
        await cog.permissions_group.list_cmd.callback(cog.permissions_group, i)
    assert "No permissions configured" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_permissions_list_fetch_error(cog, mock_bot):
    with patch(
        "bot.commands.permissions.get_server_role_ids",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db"),
    ):
        i = mock_interaction()
        with patch("bot.commands.permissions.send_error", new_callable=AsyncMock) as se:
            await cog.permissions_group.list_cmd.callback(cog.permissions_group, i)
        se.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_list_with_roles_and_users(cog, mock_bot):
    role = MagicMock()
    role.members = []
    with patch(
        "bot.commands.permissions.get_server_role_ids",
        new_callable=AsyncMock,
        return_value={Role.MODERATOR: 999},
    ):
        pool, conn = mock_db_pool(
            fetch=[{"user_id": 5, "role": "moderator"}],
        )
        mock_bot.db_pool = pool
        i = mock_interaction()
        i.guild.get_role = MagicMock(return_value=role)
        await cog.permissions_group.list_cmd.callback(cog.permissions_group, i)
    assert i.followup.send.call_args[1].get("view") is not None


@pytest.mark.asyncio
async def test_permissions_add_duplicate(cog, mock_bot):
    pool, conn = mock_db_pool(fetchval=1)
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(20, "x"))
    await cog.permissions_group.add_cmd.callback(cog.permissions_group, i, user="20", role="admin")
    assert "already has" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_permissions_add_insert_failure(cog, mock_bot):
    pool, conn = mock_db_pool(fetchval=None)
    conn.execute = AsyncMock(side_effect=RuntimeError("db"))
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(20, "x"))
    with patch("bot.commands.permissions.send_error", new_callable=AsyncMock) as se:
        await cog.permissions_group.add_cmd.callback(
            cog.permissions_group, i, user="20", role="admin"
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_remove_no_rows(cog, mock_bot):
    pool, conn = mock_db_pool(execute="UPDATE 0")
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(20, "x"))
    await cog.permissions_group.remove_cmd.callback(
        cog.permissions_group, i, user="20", role="admin"
    )
    assert_followup_contains(i, "doesn't have", case_sensitive=False)


@pytest.mark.asyncio
async def test_permissions_remove_exception(cog, mock_bot):
    pool, conn = mock_db_pool(execute="UPDATE 1")
    conn.execute = AsyncMock(side_effect=[RuntimeError("x")])
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(20, "x"))
    with patch("bot.commands.permissions.send_error", new_callable=AsyncMock) as se:
        await cog.permissions_group.remove_cmd.callback(
            cog.permissions_group, i, user="20", role="admin"
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_set_failure(cog, mock_bot):
    with patch(
        "bot.commands.permissions.set_server_role",
        new_callable=AsyncMock,
        return_value=False,
    ):
        i = mock_interaction()
        role = MagicMock(id=555)
        await cog.permissions_group.set_cmd.callback(
            cog.permissions_group, i, level="admin", discord_role=role
        )
        assert_followup_contains(i, "Failed", case_sensitive=False)


@pytest.mark.asyncio
async def test_permissions_set_clear_role(cog, mock_bot):
    with patch(
        "bot.commands.permissions.set_server_role",
        new_callable=AsyncMock,
        return_value=True,
    ):
        i = mock_interaction()
        await cog.permissions_group.set_cmd.callback(
            cog.permissions_group, i, level="moderator", discord_role=None
        )
    assert "cleared" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_permissions_set_not_super_admin(cog, mock_bot):
    mock_bot.permission_checker.check_role = AsyncMock(return_value=False)
    i = mock_interaction()
    await cog.permissions_group.set_cmd.callback(
        cog.permissions_group, i, level="admin", discord_role=None
    )


@pytest.mark.asyncio
async def test_cog_load_setup(mock_bot):
    mock_bot.tree.add_command = MagicMock()
    cog = PermissionCommands(mock_bot)
    await cog.cog_load()
    mock_bot.tree.remove_command = MagicMock()
    await cog.cog_unload()

    from bot.commands import permissions as perm_mod

    mock_bot.add_cog = AsyncMock()
    await perm_mod.setup(mock_bot)
    mock_bot.add_cog.assert_awaited_once()


def test_permissions_list_format_role_mode_empty_roles():
    view = PermissionsListView(
        role_ids={},
        role_members=[(7, Role.MODERATOR)],
        user_rows=[],
    )
    text = view._format_page()
    assert "no roles configured" in text.lower()


def test_role_members_skips_when_discord_role_missing():
    guild = MagicMock()
    guild.get_role = MagicMock(return_value=None)
    role_ids = {Role.MODERATOR: 999}
    assert _role_members(guild, role_ids) == []


@pytest.mark.asyncio
async def test_permissions_user_autocomplete_matches_username_not_display():
    m = MagicMock(bot=False)
    m.display_name = ""
    m.name = "hidden_name"
    m.id = 12
    guild = MagicMock(members=[m])
    i = MagicMock(guild=guild)
    choices = await _permissions_user_autocomplete(i, "hidden")
    assert any(c.value == "12" for c in choices)


@pytest.mark.asyncio
async def test_permissions_list_not_super_admin(cog, mock_bot):
    pool = MagicMock()
    mock_bot.db_pool = pool
    with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.permissions_group.list_cmd.callback(cog.permissions_group, i)
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_permissions_list_require_guild_false(cog, mock_bot):
    with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=True)):
        with patch("bot.commands.permissions.require_guild", AsyncMock(return_value=False)):
            i = mock_interaction()
            await cog.permissions_group.list_cmd.callback(cog.permissions_group, i)


@pytest.mark.asyncio
async def test_permissions_view_prev_next_noop_at_boundary():
    view = PermissionsListView(
        role_ids={Role.ADMIN: 1},
        role_members=[(9, Role.ADMIN)],
        user_rows=[],
    )
    view.page = 0
    i = MagicMock()
    i.response.edit_message = AsyncMock()
    await view._prev_callback(i)
    i.response.edit_message.assert_not_called()

    view._max_page = 0
    view.page = 0
    i2 = MagicMock()
    i2.response.edit_message = AsyncMock()
    await view._next_callback(i2)
    i2.response.edit_message.assert_not_called()


@pytest.mark.asyncio
async def test_permissions_add_not_super_admin(cog, mock_bot):
    pool = MagicMock()
    mock_bot.db_pool = pool
    with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=False)):
        i = mock_interaction(guild_get_member=mock_user(20, "x"))
        await cog.permissions_group.add_cmd.callback(
            cog.permissions_group, i, user="20", role="admin"
        )
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_permissions_add_require_guild_false(cog, mock_bot):
    with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=True)):
        with patch("bot.commands.permissions.require_guild", AsyncMock(return_value=False)):
            i = mock_interaction(guild_get_member=mock_user(21, "y"))
            await cog.permissions_group.add_cmd.callback(
                cog.permissions_group, i, user="21", role="admin"
            )


@pytest.mark.asyncio
async def test_permissions_add_success_with_notifier(cog, mock_bot):
    pool, conn = mock_db_pool(fetchval=None)
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(23, "z"))
    await cog.permissions_group.add_cmd.callback(cog.permissions_group, i, user="23", role="admin")
    mock_bot.notifier.notify_permission_changed.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_remove_success_with_notifier(cog, mock_bot):
    pool, conn = mock_db_pool(execute="UPDATE 1")
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(24, "r"))
    await cog.permissions_group.remove_cmd.callback(
        cog.permissions_group, i, user="24", role="admin"
    )
    mock_bot.notifier.notify_permission_changed.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_set_success_with_role_notifies(cog, mock_bot):
    with patch("bot.commands.permissions.set_server_role", AsyncMock(return_value=True)):
        i = mock_interaction()
        role = MagicMock(id=888, mention="<@&888>")
        await cog.permissions_group.set_cmd.callback(
            cog.permissions_group, i, level="admin", discord_role=role
        )
    mock_bot.notifier.notify_permission_changed.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_set_success_clear_notifies(cog, mock_bot):
    with patch("bot.commands.permissions.set_server_role", AsyncMock(return_value=True)):
        i = mock_interaction()
        await cog.permissions_group.set_cmd.callback(
            cog.permissions_group, i, level="moderator", discord_role=None
        )
    mock_bot.notifier.notify_permission_changed.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_add_success_without_notifier(cog, mock_bot):
    mock_bot.notifier = None
    pool, conn = mock_db_pool(fetchval=None)
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(31, "n"))
    await cog.permissions_group.add_cmd.callback(cog.permissions_group, i, user="31", role="admin")
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_permissions_remove_success_without_notifier(cog, mock_bot):
    mock_bot.notifier = None
    pool, conn = mock_db_pool(execute="UPDATE 1")
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(32, "r"))
    await cog.permissions_group.remove_cmd.callback(
        cog.permissions_group, i, user="32", role="admin"
    )
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_permissions_set_success_without_notifier(cog, mock_bot):
    mock_bot.notifier = None
    with patch("bot.commands.permissions.set_server_role", AsyncMock(return_value=True)):
        i = mock_interaction()
        role = MagicMock(id=333, mention="<@&333>")
        await cog.permissions_group.set_cmd.callback(
            cog.permissions_group, i, level="admin", discord_role=role
        )
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_permissions_set_guild_none_after_checks(cog, mock_bot):
    with patch("bot.commands.permissions.set_server_role", AsyncMock(return_value=True)):
        with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=True)):
            with patch("bot.commands.permissions.require_guild", AsyncMock(return_value=True)):
                i = mock_interaction()
                i.guild = None
                await cog.permissions_group.set_cmd.callback(
                    cog.permissions_group, i, level="admin", discord_role=None
                )


@pytest.mark.asyncio
async def test_permissions_remove_parse_error(cog, mock_bot):
    pool, conn = mock_db_pool()
    mock_bot.db_pool = pool
    i = mock_interaction()
    with patch("bot.commands.permissions.send_error", new_callable=AsyncMock) as se:
        await cog.permissions_group.remove_cmd.callback(
            cog.permissions_group, i, user="bad", role="admin"
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_add_parse_error(cog, mock_bot):
    pool, conn = mock_db_pool()
    mock_bot.db_pool = pool
    i = mock_interaction()
    with patch("bot.commands.permissions.send_error", new_callable=AsyncMock) as se:
        await cog.permissions_group.add_cmd.callback(
            cog.permissions_group, i, user="notanid", role="admin"
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_permissions_list_view_next_page_advances():
    role_members = [(n, Role.MODERATOR) for n in range(15)]
    view = PermissionsListView(
        role_ids={Role.MODERATOR: 1},
        role_members=role_members,
        user_rows=[],
    )
    assert view._max_page >= 1
    i = MagicMock()
    i.response.edit_message = AsyncMock()
    await view._next_callback(i)
    assert view.page == 1


def test_permissions_list_view_update_buttons_without_page_btn():
    view = PermissionsListView(
        role_ids={Role.ADMIN: 1},
        role_members=[(1, Role.ADMIN)],
        user_rows=[],
    )
    view.page_btn = None
    view._update_buttons()


@pytest.mark.asyncio
async def test_permissions_remove_not_super_admin(cog, mock_bot):
    pool = MagicMock()
    mock_bot.db_pool = pool
    with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=False)):
        i = mock_interaction(guild_get_member=mock_user(41, "x"))
        await cog.permissions_group.remove_cmd.callback(
            cog.permissions_group, i, user="41", role="admin"
        )
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_permissions_remove_require_guild_false(cog, mock_bot):
    with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=True)):
        with patch("bot.commands.permissions.require_guild", AsyncMock(return_value=False)):
            i = mock_interaction(guild_get_member=mock_user(42, "y"))
            await cog.permissions_group.remove_cmd.callback(
                cog.permissions_group, i, user="42", role="admin"
            )


@pytest.mark.asyncio
async def test_permissions_set_require_guild_false(cog, mock_bot):
    with patch("bot.commands.permissions.require_super_admin", AsyncMock(return_value=True)):
        with patch("bot.commands.permissions.require_guild", AsyncMock(return_value=False)):
            i = mock_interaction()
            await cog.permissions_group.set_cmd.callback(
                cog.permissions_group, i, level="admin", discord_role=None
            )


@pytest.mark.asyncio
async def test_permissions_user_autocomplete_skips_non_matching_member():
    alice = MagicMock(bot=False)
    alice.display_name = "DisplayZZZ"
    alice.name = "alice_smith"
    alice.id = 88
    bob = MagicMock(bot=False)
    bob.display_name = "Bob"
    bob.name = "bob_only"
    bob.id = 99
    guild = MagicMock(members=[alice, bob])
    i = MagicMock(guild=guild)
    choices = await _permissions_user_autocomplete(i, "alice")
    assert [c.value for c in choices] == ["88"]


@pytest.mark.asyncio
async def test_permissions_user_autocomplete_matches_name_when_display_differs():
    m = MagicMock(bot=False)
    m.display_name = "DisplayZZZ"
    m.name = "alice_smith"
    m.id = 88
    guild = MagicMock(members=[m])
    i = MagicMock(guild=guild)
    choices = await _permissions_user_autocomplete(i, "alice")
    assert any(c.value == "88" for c in choices)


@pytest.mark.asyncio
async def test_permissions_remove_db_exception_before_execute_result(cog, mock_bot):
    pool, conn = mock_db_pool(execute="UPDATE 1")
    conn.execute = AsyncMock(side_effect=RuntimeError("db"))
    mock_bot.db_pool = pool
    i = mock_interaction(guild_get_member=mock_user(40, "x"))
    with patch("bot.commands.permissions.send_error", new_callable=AsyncMock) as se:
        await cog.permissions_group.remove_cmd.callback(
            cog.permissions_group, i, user="40", role="admin"
        )
    se.assert_awaited()
