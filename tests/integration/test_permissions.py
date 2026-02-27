"""Integration tests for permissions."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.auth.permissions import PermissionChecker, PermissionContext
from config.constants import Role


@pytest.mark.asyncio
async def test_permission_check_super_admin(mock_cache):
    """Test super admin role check."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "super_admin"

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire

    checker = PermissionChecker(mock_db_pool, mock_cache)

    ctx = PermissionContext(server_id=123456789, user_id=987654321)

    result = await checker.check_role(ctx, Role.ADMIN)
    assert result is True


@pytest.mark.asyncio
async def test_permission_check_insufficient(mock_cache):
    """Test insufficient permissions."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "moderator"

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire

    checker = PermissionChecker(mock_db_pool, mock_cache)

    ctx = PermissionContext(server_id=123456789, user_id=987654321)

    result = await checker.check_role(ctx, Role.ADMIN)
    assert result is False


@pytest.mark.asyncio
async def test_command_permission_allowed(mock_cache):
    """Test specific command permission allowed (via super admin)."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "super_admin"

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire

    checker = PermissionChecker(mock_db_pool, mock_cache)

    ctx = PermissionContext(server_id=123456789, user_id=987654321, command_name="reactbot_add")

    result = await checker.check_command_permission(ctx)
    assert result is True
