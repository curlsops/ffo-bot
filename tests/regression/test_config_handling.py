from unittest.mock import AsyncMock, MagicMock

import pytest

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
