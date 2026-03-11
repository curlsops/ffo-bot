from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.auth.permissions import PermissionChecker, PermissionContext
from config.constants import Role


def _pool(fetchval):
    conn = AsyncMock()
    conn.fetchval.return_value = fetchval

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool


@pytest.mark.asyncio
async def test_permission_check_super_admin(mock_cache):
    pool = _pool("super_admin")
    checker = PermissionChecker(pool, mock_cache)
    ctx = PermissionContext(server_id=123456789, user_id=987654321)
    assert await checker.check_role(ctx, Role.ADMIN) is True


@pytest.mark.asyncio
async def test_permission_check_insufficient(mock_cache):
    pool = _pool("moderator")
    checker = PermissionChecker(pool, mock_cache)
    ctx = PermissionContext(server_id=123456789, user_id=987654321)
    assert await checker.check_role(ctx, Role.ADMIN) is False


@pytest.mark.asyncio
async def test_command_permission_allowed(mock_cache):
    pool = _pool("super_admin")
    checker = PermissionChecker(pool, mock_cache)
    ctx = PermissionContext(server_id=123456789, user_id=987654321, command_name="reactbot add")
    assert await checker.check_command_permission(ctx) is True
