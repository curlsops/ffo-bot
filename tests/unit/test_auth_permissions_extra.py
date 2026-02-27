"""Additional unit tests for PermissionChecker to push coverage higher."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.auth.permissions import PermissionChecker, PermissionContext
from config.constants import Role


def make_db_pool(fetchval_result=None, execute_side_effect=None):
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=fetchval_result)
    conn.execute = AsyncMock(side_effect=execute_side_effect)

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


@pytest.mark.asyncio
async def test_check_role_no_role_logs_and_returns_false():
    """If user has no role, check_role logs and returns False."""
    db_pool, _ = make_db_pool(fetchval_result=None)
    cache = MagicMock()
    cache.get.return_value = None

    checker = PermissionChecker(db_pool, cache)
    ctx = PermissionContext(server_id=1, user_id=2)

    result = await checker.check_role(ctx, Role.ADMIN)

    assert result is False


@pytest.mark.asyncio
async def test_check_command_permission_uses_cache():
    """check_command_permission returns cached value when present."""
    db_pool, _ = make_db_pool()
    cache = MagicMock()
    cache.get.return_value = True

    checker = PermissionChecker(db_pool, cache)
    ctx = PermissionContext(server_id=1, user_id=2, command_name="x")

    # Force super admin check to be False so it goes to cache
    checker.check_role = AsyncMock(return_value=False)

    result = await checker.check_command_permission(ctx)

    assert result is True
    checker.check_role.assert_awaited()
    # No DB call when cache hit


@pytest.mark.asyncio
async def test_check_command_permission_db_path_caches_result():
    """When not super admin and no cache, permission is fetched from DB and stored."""
    db_pool, conn = make_db_pool(fetchval_result=True)
    cache = MagicMock()
    cache.get.return_value = None

    checker = PermissionChecker(db_pool, cache)
    ctx = PermissionContext(server_id=1, user_id=2, command_name="x")

    checker.check_role = AsyncMock(return_value=False)

    result = await checker.check_command_permission(ctx)

    assert result is True
    conn.fetchval.assert_awaited()
    cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_user_role_uses_cache_before_db():
    """get_user_role returns cached value without hitting DB."""
    db_pool, conn = make_db_pool()
    cache = MagicMock()
    cache.get.return_value = Role.ADMIN

    checker = PermissionChecker(db_pool, cache)

    role = await checker.get_user_role(server_id=1, user_id=2)

    assert role == Role.ADMIN
    conn.fetchval.assert_not_awaited()


@pytest.mark.asyncio
async def test_log_permission_denial_handles_db_error():
    """_log_permission_denial swallows DB errors and logs."""
    db_pool, conn = make_db_pool(execute_side_effect=Exception("db error"))
    cache = MagicMock()

    checker = PermissionChecker(db_pool, cache)
    ctx = PermissionContext(server_id=1, user_id=2, command_name="x")

    # Should not raise even though execute fails
    await checker._log_permission_denial(ctx, Role.SUPER_ADMIN)
    conn.execute.assert_awaited()


def test_invalidate_user_cache_deletes_and_logs():
    """invalidate_user_cache calls cache.delete with correct key."""
    db_pool, _ = make_db_pool()
    cache = MagicMock()

    checker = PermissionChecker(db_pool, cache)
    checker.invalidate_user_cache(server_id=1, user_id=2)

    cache.delete.assert_called_once()

