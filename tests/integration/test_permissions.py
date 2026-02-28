from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.auth.permissions import PermissionChecker, PermissionContext
from config.constants import Role


@pytest.mark.asyncio
async def test_permission_check_super_admin(mock_cache):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "super_admin"

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire
    checker = PermissionChecker(mock_db_pool, mock_cache)
    ctx = PermissionContext(server_id=123456789, user_id=987654321)
    assert await checker.check_role(ctx, Role.ADMIN) is True


@pytest.mark.asyncio
async def test_permission_check_insufficient(mock_cache):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "moderator"

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire
    checker = PermissionChecker(mock_db_pool, mock_cache)
    ctx = PermissionContext(server_id=123456789, user_id=987654321)
    assert await checker.check_role(ctx, Role.ADMIN) is False


@pytest.mark.asyncio
async def test_command_permission_allowed(mock_cache):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "super_admin"

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire
    checker = PermissionChecker(mock_db_pool, mock_cache)
    ctx = PermissionContext(server_id=123456789, user_id=987654321, command_name="reactbot_add")
    assert await checker.check_command_permission(ctx) is True
