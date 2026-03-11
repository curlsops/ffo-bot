from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from bot.auth.permissions import PermissionChecker, PermissionContext
from config.constants import Role


def _make_db_pool(fetchval_result=None, fetchval_side_effect=None, execute_side_effect=None):
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=fetchval_result, side_effect=fetchval_side_effect)
    conn.execute = AsyncMock(side_effect=execute_side_effect)

    @asynccontextmanager
    async def acquire(**kwargs):
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


def _checker(
    fetchval_result=None,
    cache_return=None,
    bot=None,
    execute_side_effect=None,
    fetchval_side_effect=None,
):
    db_pool, conn = _make_db_pool(fetchval_result, fetchval_side_effect, execute_side_effect)
    cache = MagicMock()
    cache.get.return_value = cache_return
    return PermissionChecker(db_pool, cache, bot), conn, cache


def _checker_with_bot(guild=None, member=None):
    bot = MagicMock()
    bot.get_guild.return_value = guild
    if guild:
        guild.get_member.return_value = member
    checker, _, _ = _checker(bot=bot)
    return checker


def _ctx(server_id=1, user_id=2, command_name=None):
    return PermissionContext(server_id=server_id, user_id=user_id, command_name=command_name)


class TestIsDiscordAdmin:
    @pytest.mark.parametrize(
        "guild,member,is_admin,expected",
        [
            (None, None, False, False),
            (MagicMock(), None, False, False),
            (
                MagicMock(),
                MagicMock(guild_permissions=MagicMock(administrator=False)),
                False,
                False,
            ),
            (MagicMock(), MagicMock(guild_permissions=MagicMock(administrator=True)), True, True),
        ],
    )
    def test_cases(self, guild, member, is_admin, expected):
        checker = _checker_with_bot(guild, member)
        assert checker._is_discord_admin(1, 2) is expected

    def test_no_bot(self):
        checker, _, _ = _checker()
        assert checker._is_discord_admin(1, 2) is False

    def test_member_not_in_guild(self):
        guild = MagicMock()
        guild.get_member.return_value = None
        checker = _checker_with_bot(guild, None)
        assert checker._is_discord_admin(1, 2) is False


class TestCheckRole:
    @pytest.mark.asyncio
    async def test_discord_admin_bypasses(self):
        member = MagicMock(guild_permissions=MagicMock(administrator=True))
        checker = _checker_with_bot(MagicMock(), member)
        assert await checker.check_role(_ctx(), Role.SUPER_ADMIN) is True

    @pytest.mark.asyncio
    async def test_no_role_returns_false(self):
        checker, _, _ = _checker(fetchval_result=None)
        assert await checker.check_role(_ctx(), Role.ADMIN) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_role,required_role,expected,should_log",
        [
            ("super_admin", Role.ADMIN, True, False),
            ("admin", Role.ADMIN, True, False),
            ("admin", Role.MODERATOR, True, False),
            ("moderator", Role.MODERATOR, True, False),
            ("moderator", Role.ADMIN, False, True),
            ("moderator", Role.SUPER_ADMIN, False, True),
        ],
    )
    async def test_hierarchy(self, user_role, required_role, expected, should_log):
        checker, conn, _ = _checker(fetchval_result=user_role)
        result = await checker.check_role(_ctx(command_name="cmd"), required_role)
        assert result is expected
        if should_log:
            conn.execute.assert_awaited()
        else:
            conn.execute.assert_not_awaited()


class TestCheckCommandPermission:
    @pytest.mark.asyncio
    async def test_super_admin_bypasses(self):
        checker, _, _ = _checker(fetchval_result="super_admin")
        assert await checker.check_command_permission(_ctx(command_name="any")) is True

    @pytest.mark.asyncio
    async def test_uses_cache(self):
        checker, conn, _ = _checker(cache_return=True)
        checker.check_role = AsyncMock(return_value=False)
        assert await checker.check_command_permission(_ctx(command_name="x")) is True
        conn.fetchval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_path_caches_result(self):
        checker, conn, cache = _checker(fetchval_result=True)
        checker.check_role = AsyncMock(return_value=False)
        assert await checker.check_command_permission(_ctx(command_name="x")) is True
        conn.fetchval.assert_awaited()
        cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_command_name(self):
        checker, _, cache = _checker(fetchval_result=False)
        checker.check_role = AsyncMock(return_value=False)
        assert await checker.check_command_permission(_ctx(command_name=None)) is False
        cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_unavailable_denies(self):
        checker, _, _ = _checker(fetchval_side_effect=asyncpg.CannotConnectNowError("down"))
        checker.check_role = AsyncMock(return_value=False)
        assert await checker.check_command_permission(_ctx(command_name="x")) is False


class TestGetUserRole:
    @pytest.mark.asyncio
    async def test_uses_cache(self):
        checker, conn, _ = _checker(cache_return=Role.ADMIN)
        assert await checker.get_user_role(1, 2) == Role.ADMIN
        conn.fetchval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_from_db_caches(self):
        checker, _, cache = _checker(fetchval_result="admin")
        assert await checker.get_user_role(1, 2) == Role.ADMIN
        cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_from_db(self):
        checker, _, _ = _checker(fetchval_result=None)
        assert await checker.get_user_role(1, 2) is None

    @pytest.mark.asyncio
    async def test_db_unavailable_returns_none(self):
        checker, _, _ = _checker(fetchval_side_effect=asyncpg.CannotConnectNowError("down"))
        assert await checker.get_user_role(1, 2) is None

    @pytest.mark.asyncio
    async def test_from_server_roles_when_member_has_role(self):
        checker, conn, cache = _checker(bot=MagicMock())
        guild = MagicMock()
        role_obj = MagicMock()
        role_obj.id = 111
        member = MagicMock()
        member.roles = [role_obj]
        guild.get_member.return_value = member
        checker.bot.get_guild.return_value = guild

        with patch(
            "bot.utils.server_roles.get_server_role_ids",
            new_callable=AsyncMock,
            return_value={Role.ADMIN: 111},
        ):
            result = await checker.get_user_role(1, 2)
        assert result == Role.ADMIN
        conn.fetchval.assert_not_awaited()
        cache.set.assert_called_once_with("user_role:1:2", Role.ADMIN, ttl=86400)

    @pytest.mark.asyncio
    async def test_from_server_roles_falls_to_db_when_member_has_no_matching_role(self):
        checker, conn, cache = _checker(bot=MagicMock(), fetchval_result="admin")
        guild = MagicMock()
        member = MagicMock()
        member.roles = [MagicMock(id=999)]
        guild.get_member.return_value = member
        checker.bot.get_guild.return_value = guild

        with patch(
            "bot.utils.server_roles.get_server_role_ids",
            new_callable=AsyncMock,
            return_value={Role.ADMIN: 111},
        ):
            result = await checker.get_user_role(1, 2)
        assert result == Role.ADMIN
        conn.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_from_server_roles_matches_super_admin_first(self):
        checker, conn, cache = _checker(bot=MagicMock())
        guild = MagicMock()
        role_obj = MagicMock()
        role_obj.id = 333
        member = MagicMock()
        member.roles = [role_obj]
        guild.get_member.return_value = member
        checker.bot.get_guild.return_value = guild

        with patch(
            "bot.utils.server_roles.get_server_role_ids",
            new_callable=AsyncMock,
            return_value={Role.SUPER_ADMIN: 333, Role.ADMIN: 111},
        ):
            result = await checker.get_user_role(1, 2)
        assert result == Role.SUPER_ADMIN
        conn.fetchval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_from_server_roles_matches_moderator_third_in_loop(self):
        checker, conn, cache = _checker(bot=MagicMock())
        guild = MagicMock()
        role_obj = MagicMock()
        role_obj.id = 555
        member = MagicMock()
        member.roles = [role_obj]
        guild.get_member.return_value = member
        checker.bot.get_guild.return_value = guild

        with patch(
            "bot.utils.server_roles.get_server_role_ids",
            new_callable=AsyncMock,
            return_value={
                Role.SUPER_ADMIN: 111,
                Role.ADMIN: 222,
                Role.MODERATOR: 555,
            },
        ):
            result = await checker.get_user_role(1, 2)
        assert result == Role.MODERATOR
        conn.fetchval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_from_server_roles_no_match_falls_back_to_db(self):
        checker, conn, cache = _checker(bot=MagicMock())
        guild = MagicMock()
        member = MagicMock()
        member.roles = []
        guild.get_member.return_value = member
        checker.bot.get_guild.return_value = guild
        conn.fetchval.return_value = "admin"

        with patch(
            "bot.utils.server_roles.get_server_role_ids",
            new_callable=AsyncMock,
            return_value={Role.SUPER_ADMIN: 111, Role.ADMIN: 222, Role.MODERATOR: 333},
        ):
            result = await checker.get_user_role(1, 2)
        assert result == Role.ADMIN
        conn.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_role_ids_falls_back_to_db(self):
        checker, conn, cache = _checker(bot=MagicMock())
        conn.fetchval.return_value = "moderator"

        with patch(
            "bot.utils.server_roles.get_server_role_ids",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await checker.get_user_role(1, 2)
        assert result == Role.MODERATOR
        checker.bot.get_guild.assert_not_called()

    @pytest.mark.asyncio
    async def test_member_not_in_guild_falls_back_to_db(self):
        checker, conn, cache = _checker(bot=MagicMock())
        guild = MagicMock()
        guild.get_member.return_value = None
        checker.bot.get_guild.return_value = guild
        conn.fetchval.return_value = "admin"

        with patch(
            "bot.utils.server_roles.get_server_role_ids",
            new_callable=AsyncMock,
            return_value={Role.ADMIN: 111},
        ):
            result = await checker.get_user_role(1, 2)
        assert result == Role.ADMIN
        conn.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_user_role_db_transient_error_caches_none(self):
        checker, _, cache = _checker(fetchval_side_effect=asyncpg.CannotConnectNowError("down"))
        result = await checker.get_user_role(1, 2)
        assert result is None
        cache.set.assert_called_once_with("user_role:1:2", None, ttl=86400)


class TestLogPermissionDenial:
    @pytest.mark.asyncio
    async def test_transient_db_error_suppressed(self):
        checker, conn, _ = _checker(
            execute_side_effect=asyncpg.CannotConnectNowError("connection lost")
        )
        await checker._log_permission_denial(_ctx(command_name="x"), Role.SUPER_ADMIN)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_handles_db_error(self):
        checker, conn, _ = _checker(execute_side_effect=Exception("db error"))
        await checker._log_permission_denial(_ctx(command_name="x"), Role.SUPER_ADMIN)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_logs_non_transient_exception(self, caplog):
        import logging

        caplog.set_level(logging.ERROR, logger="bot.auth.permissions")
        checker, _, _ = _checker(execute_side_effect=RuntimeError("audit table missing"))
        await checker._log_permission_denial(_ctx(command_name="test_cmd"), Role.ADMIN)
        assert "Failed to log permission denial" in caplog.text
        assert "audit table missing" in caplog.text

    @pytest.mark.asyncio
    async def test_log_permission_denial_exception_logged(self):
        from bot.auth import permissions as perm_module

        checker, _, _ = _checker(execute_side_effect=ValueError("constraint violation"))
        with patch.object(perm_module.logger, "error") as mock_log:
            await checker._log_permission_denial(_ctx(command_name="x"), Role.SUPER_ADMIN)
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "Failed to log permission denial: %s"
            assert str(mock_log.call_args[0][1]) == "constraint violation"

    @pytest.mark.asyncio
    async def test_check_role_logs_denial_when_audit_fails(self, caplog):
        import logging

        caplog.set_level(logging.ERROR, logger="bot.auth.permissions")
        checker, conn, _ = _checker(
            fetchval_result="moderator",
            execute_side_effect=RuntimeError("audit table missing"),
        )
        result = await checker.check_role(_ctx(command_name="admin_cmd"), Role.ADMIN)
        assert result is False
        assert "Failed to log permission denial" in caplog.text


class TestInvalidateUserCache:
    def test_deletes_cache_key(self):
        checker, _, cache = _checker()
        checker.invalidate_user_cache(1, 2)
        cache.delete.assert_called_once_with("user_role:1:2")


class TestRoleHierarchy:
    def test_order(self):
        assert Role.SUPER_ADMIN.hierarchy > Role.ADMIN.hierarchy > Role.MODERATOR.hierarchy
        assert (Role.SUPER_ADMIN.hierarchy, Role.ADMIN.hierarchy, Role.MODERATOR.hierarchy) == (
            3,
            2,
            1,
        )


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_get_user_role_invalid_role_string(self):
        checker, _, _ = _checker(fetchval_result="invalid_role")
        with pytest.raises(ValueError):
            await checker.get_user_role(1, 2)

    @pytest.mark.asyncio
    async def test_get_user_role_empty_string(self):
        checker, _, _ = _checker(fetchval_result="")
        result = await checker.get_user_role(1, 2)
        assert result is None

    @pytest.mark.asyncio
    async def test_check_role_with_guild_id_zero(self):
        checker, _, _ = _checker(fetchval_result="admin")
        ctx = _ctx(server_id=0, user_id=2)
        result = await checker.check_role(ctx, Role.MODERATOR)
        assert result is True
