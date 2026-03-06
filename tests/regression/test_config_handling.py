from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.notifier import AdminNotifier
from bot.utils.quotebook_channel import get_quotebook_channel_id
from bot.utils.server_roles import get_server_role_ids
from bot.utils.whitelist_channel import get_whitelist_channel_id


def _make_pool(fetchrow_result):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [{"config": {}}, {"config": None}, {"config": "invalid"}, None])
async def test_get_server_role_ids_edge_cases(row):
    result = await get_server_role_ids(_make_pool(row), 123)
    assert result == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("getter", [get_whitelist_channel_id, get_quotebook_channel_id])
@pytest.mark.parametrize("row", [{"config": {}}, {"config": None}])
async def test_channel_getters_empty_or_none_config(getter, row):
    result = await getter(_make_pool(row), 123)
    assert result is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_repairs_corrupted_config():
    row = {"config": [{}, '{"whitelist_channel_id": 789}']}
    result = await get_whitelist_channel_id(_make_pool(row), 123)
    assert result == 789


@pytest.mark.asyncio
async def test_get_quotebook_channel_id_repairs_corrupted_config():
    row = {"config": [{}, '{"quotebook_channel_id": 456}']}
    result = await get_quotebook_channel_id(_make_pool(row), 123)
    assert result == 456


@pytest.mark.asyncio
async def test_get_notify_channel_id_repairs_corrupted_config():
    bot = MagicMock()
    bot.cache = None
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"config": [{}, '{"notify_channel_id": 999}']})
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    bot.db_pool = MagicMock(acquire=MagicMock(return_value=ctx))
    result = await AdminNotifier(bot).get_notify_channel_id(123)
    assert result == 999
