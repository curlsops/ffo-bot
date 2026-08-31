from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services.permissions_repository import PermissionsRepository


def _make_db_pool(fetchval_result=None, fetch_result=None, execute_result=None):
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=fetchval_result)
    conn.fetch = AsyncMock(return_value=fetch_result or [])
    conn.execute = AsyncMock(return_value=execute_result)

    @asynccontextmanager
    async def acquire(**kwargs):
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


class TestHasCommandPermission:
    @pytest.mark.asyncio
    async def test_true_when_exists(self):
        pool, conn = _make_db_pool(fetchval_result=True)
        repo = PermissionsRepository(pool)
        result = await repo.has_command_permission(1, 2, "cmd")
        assert result is True
        conn.fetchval.assert_awaited_once()
        args = conn.fetchval.call_args.args
        assert args[1:] == (1, 2, "cmd")

    @pytest.mark.asyncio
    async def test_false_when_missing(self):
        pool, conn = _make_db_pool(fetchval_result=False)
        repo = PermissionsRepository(pool)
        result = await repo.has_command_permission(1, 2, "cmd")
        assert result is False


class TestFetchUserRole:
    @pytest.mark.asyncio
    async def test_returns_role_string(self):
        pool, conn = _make_db_pool(fetchval_result="admin")
        repo = PermissionsRepository(pool)
        result = await repo.fetch_user_role(1, 2)
        assert result == "admin"
        args = conn.fetchval.call_args.args
        assert args[1:] == (1, 2)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_role(self):
        pool, conn = _make_db_pool(fetchval_result=None)
        repo = PermissionsRepository(pool)
        result = await repo.fetch_user_role(1, 2)
        assert result is None


class TestLogPermissionDenial:
    @pytest.mark.asyncio
    async def test_inserts_audit_row(self):
        pool, conn = _make_db_pool()
        repo = PermissionsRepository(pool)
        details = {"command": "x", "required_role": "admin"}
        await repo.log_permission_denial(1, 2, details)
        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert args[1:] == (1, 2, details)


class TestListActiveGrants:
    @pytest.mark.asyncio
    async def test_returns_rows_as_dicts(self):
        pool, conn = _make_db_pool(fetch_result=[{"user_id": 9, "role": "admin"}])
        repo = PermissionsRepository(pool)
        result = await repo.list_active_grants(1)
        assert result == [{"user_id": 9, "role": "admin"}]
        args = conn.fetch.call_args.args
        assert args[1:] == (1,)

    @pytest.mark.asyncio
    async def test_empty(self):
        pool, conn = _make_db_pool(fetch_result=[])
        repo = PermissionsRepository(pool)
        result = await repo.list_active_grants(1)
        assert result == []


class TestFindActiveGrant:
    @pytest.mark.asyncio
    async def test_true_when_exists(self):
        pool, conn = _make_db_pool(fetchval_result=1)
        repo = PermissionsRepository(pool)
        result = await repo.find_active_grant(1, 2, "admin")
        assert result is True
        args = conn.fetchval.call_args.args
        assert args[1:] == (1, 2, "admin")

    @pytest.mark.asyncio
    async def test_false_when_missing(self):
        pool, conn = _make_db_pool(fetchval_result=None)
        repo = PermissionsRepository(pool)
        result = await repo.find_active_grant(1, 2, "admin")
        assert result is False


class TestInsertGrant:
    @pytest.mark.asyncio
    async def test_inserts(self):
        pool, conn = _make_db_pool()
        repo = PermissionsRepository(pool)
        await repo.insert_grant(1, 2, "admin", 3)
        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert args[1:] == (1, 2, "admin", 3)


class TestRevokeGrant:
    @pytest.mark.asyncio
    async def test_true_when_row_updated(self):
        pool, conn = _make_db_pool(execute_result="UPDATE 1")
        repo = PermissionsRepository(pool)
        result = await repo.revoke_grant(1, 2, "admin")
        assert result is True
        args = conn.execute.call_args.args
        assert args[1:] == (1, 2, "admin")

    @pytest.mark.asyncio
    async def test_false_when_no_row(self):
        pool, conn = _make_db_pool(execute_result="UPDATE 0")
        repo = PermissionsRepository(pool)
        result = await repo.revoke_grant(1, 2, "admin")
        assert result is False
