from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.server_roles import (
    _extract_role_ids_from_config,
    get_server_role_ids,
    set_server_role,
)
from config.constants import Role


def _make_pool(fetchrow_result=None, execute_result=None):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    conn.execute = AsyncMock(return_value=execute_result)

    @asynccontextmanager
    async def acquire(**kwargs):
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


def test_extract_role_ids_returns_empty_for_non_dict():
    assert _extract_role_ids_from_config("invalid") == {}
    assert _extract_role_ids_from_config(None) == {}


@pytest.mark.asyncio
async def test_get_server_role_ids_success():
    pool, _ = _make_pool(
        fetchrow_result={"config": {"admin_role_id": 111, "moderator_role_id": 222}}
    )
    result = await get_server_role_ids(pool, 123)
    assert result == {Role.ADMIN: 111, Role.MODERATOR: 222}


@pytest.mark.asyncio
async def test_get_server_role_ids_empty_config():
    pool, _ = _make_pool(fetchrow_result={"config": {}})
    result = await get_server_role_ids(pool, 123)
    assert result == {}


@pytest.mark.asyncio
async def test_get_server_role_ids_none_row():
    pool, _ = _make_pool(fetchrow_result=None)
    result = await get_server_role_ids(pool, 123)
    assert result == {}


@pytest.mark.asyncio
async def test_set_server_role_add():
    pool, conn = _make_pool()
    result = await set_server_role(pool, 123, Role.ADMIN, 999)
    assert result is True
    conn.execute.assert_awaited_once()
    call_args = str(conn.execute.call_args)
    assert "999" in call_args or "admin_role_id" in call_args


@pytest.mark.asyncio
async def test_set_server_role_add_invalidates_cache():
    pool, conn = _make_pool()
    cache = MagicMock()
    result = await set_server_role(pool, 123, Role.ADMIN, 999, cache=cache)
    assert result is True
    cache.delete.assert_called_once_with("server_roles:123")


@pytest.mark.asyncio
async def test_set_server_role_clear():
    pool, conn = _make_pool()
    result = await set_server_role(pool, 123, Role.MODERATOR, None)
    assert result is True
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_server_role_clear_invalidates_cache():
    pool, conn = _make_pool()
    cache = MagicMock()
    result = await set_server_role(pool, 123, Role.MODERATOR, None, cache=cache)
    assert result is True
    cache.delete.assert_called_once_with("server_roles:123")


@pytest.mark.asyncio
async def test_get_server_role_ids_cache_hit():
    cache = MagicMock()
    cache.get.return_value = {Role.ADMIN: 999}
    pool, conn = _make_pool(fetchrow_result={"config": {"admin_role_id": 111}})
    result = await get_server_role_ids(pool, 123, cache=cache)
    assert result == {Role.ADMIN: 999}
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_server_role_ids_cache_miss_fetches_from_db():
    cache = MagicMock()
    cache.get.return_value = None
    pool, _ = _make_pool(fetchrow_result={"config": {"admin_role_id": 111}})
    result = await get_server_role_ids(pool, 123, cache=cache)
    assert result == {Role.ADMIN: 111}


@pytest.mark.asyncio
async def test_get_server_role_ids_config_not_dict():
    pool, _ = _make_pool(fetchrow_result={"config": "invalid"})
    result = await get_server_role_ids(pool, 123)
    assert result == {}


@pytest.mark.asyncio
async def test_get_server_role_ids_repairs_corrupted_list_config():
    pool, _ = _make_pool(fetchrow_result={"config": [{}, '{"admin_role_id": 456}']})
    result = await get_server_role_ids(pool, 123)
    assert result == {Role.ADMIN: 456}


@pytest.mark.asyncio
async def test_get_server_role_ids_invalid_role_id_skipped():
    pool, _ = _make_pool(
        fetchrow_result={"config": {"admin_role_id": "not_an_int", "moderator_role_id": 222}}
    )
    result = await get_server_role_ids(pool, 123)
    assert result == {Role.MODERATOR: 222}


@pytest.mark.asyncio
async def test_get_server_role_ids_invalid_role_id_type_error_skipped():
    pool, _ = _make_pool(fetchrow_result={"config": {"admin_role_id": {"nested": "dict"}}})
    result = await get_server_role_ids(pool, 123)
    assert result == {}


@pytest.mark.asyncio
async def test_set_server_role_invalid_role_returns_false():
    pool, conn = _make_pool()
    result = await set_server_role(pool, 123, "invalid_role", 999)
    assert result is False
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_server_role_db_error_returns_false():
    pool, conn = _make_pool()
    conn.execute = AsyncMock(side_effect=Exception("DB down"))
    result = await set_server_role(pool, 123, Role.ADMIN, 999)
    assert result is False


@pytest.mark.asyncio
async def test_get_server_role_ids_db_error_returns_empty():
    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(side_effect=Exception("DB down"))
    result = await get_server_role_ids(pool, 123)
    assert result == {}
