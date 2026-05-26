import pytest

from bot.utils.whitelist_cache import get_cached_usernames
from bot.utils.whitelist_channel import get_whitelist_channel_id
from tests.helpers import db_pool_with_conn, mock_db_conn


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_no_row():
    assert await get_whitelist_channel_id(db_pool_with_conn(mock_db_conn(fetchrow=None)), 1) is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_empty_config():
    pool = db_pool_with_conn(mock_db_conn(fetchrow={"config": {}}))
    assert await get_whitelist_channel_id(pool, 1) is None


@pytest.mark.asyncio
async def test_get_whitelist_channel_id_with_channel():
    pool = db_pool_with_conn(mock_db_conn(fetchrow={"config": {"whitelist_channel_id": 999}}))
    assert await get_whitelist_channel_id(pool, 1) == 999


@pytest.mark.asyncio
async def test_get_cached_usernames_empty_db_returns_empty():
    pool = db_pool_with_conn(mock_db_conn(fetch=[]))
    assert await get_cached_usernames(pool, 1, None) == []
