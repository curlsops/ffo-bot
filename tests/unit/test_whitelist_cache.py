import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.whitelist_cache import (
    add_to_cache,
    get_cache_entry,
    get_cached_usernames,
    reconcile_whitelist_cache,
    remove_from_cache,
    sync_from_rcon,
)


def make_pool(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_get_cached_usernames_success():
    conn = AsyncMock()
    conn.fetch.return_value = [{"username": "Alice"}, {"username": "Bob"}]
    pool = make_pool(conn)

    result = await get_cached_usernames(pool, 123)
    assert result == ["Alice", "Bob"]
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_cached_usernames_empty():
    conn = AsyncMock()
    conn.fetch.return_value = []
    pool = make_pool(conn)

    result = await get_cached_usernames(pool, 123)
    assert result == []


@pytest.mark.asyncio
async def test_get_cached_usernames_exception_returns_empty(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.whitelist_cache")
    conn = AsyncMock()
    conn.fetch.side_effect = Exception("DB error")
    pool = make_pool(conn)

    result = await get_cached_usernames(pool, 123)
    assert result == []
    assert "Failed to get whitelist cache" in caplog.text


@pytest.mark.asyncio
async def test_get_cached_usernames_cache_hit():
    pool = make_pool(AsyncMock())
    cache = MagicMock()
    cache.get.return_value = ["Cached", "Names"]
    result = await get_cached_usernames(pool, 123, cache=cache)
    assert result == ["Cached", "Names"]
    cache.get.assert_called_once_with("whitelist_usernames:123")
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_get_cached_usernames_cache_miss_sets_cache():
    conn = AsyncMock()
    conn.fetch.return_value = [{"username": "Alice"}]
    pool = make_pool(conn)
    cache = MagicMock()
    cache.get.return_value = None
    result = await get_cached_usernames(pool, 123, cache=cache)
    assert result == ["Alice"]
    cache.set.assert_called_once_with("whitelist_usernames:123", ["Alice"], ttl=86400)


@pytest.mark.asyncio
async def test_add_to_cache_success():
    conn = AsyncMock()
    pool = make_pool(conn)

    await add_to_cache(pool, 123, "Steve", added_by=456)
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert 123 in call_args
    assert "Steve" in call_args
    assert 456 in call_args


@pytest.mark.asyncio
async def test_add_to_cache_invalidates_cache():
    conn = AsyncMock()
    pool = make_pool(conn)
    cache = MagicMock()
    await add_to_cache(pool, 123, "Steve", cache=cache)
    cache.delete.assert_called_once_with("whitelist_usernames:123")


@pytest.mark.asyncio
async def test_add_to_cache_with_minecraft_uuid():
    conn = AsyncMock()
    pool = make_pool(conn)

    await add_to_cache(
        pool, 123, "Steve", added_by=456, minecraft_uuid="069a79f4-44e9-4726-a5be-fca90e38aaf5"
    )
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert "069a79f4-44e9-4726-a5be-fca90e38aaf5" in call_args


@pytest.mark.asyncio
async def test_add_to_cache_exception_logs(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.whitelist_cache")
    conn = AsyncMock()
    conn.execute.side_effect = Exception("DB error")
    pool = make_pool(conn)

    await add_to_cache(pool, 123, "Steve")
    assert "Failed to add to whitelist cache" in caplog.text


@pytest.mark.asyncio
async def test_remove_from_cache_success():
    conn = AsyncMock()
    pool = make_pool(conn)

    await remove_from_cache(pool, 123, "Steve")
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert 123 in call_args
    assert "Steve" in call_args


@pytest.mark.asyncio
async def test_remove_from_cache_invalidates_cache():
    conn = AsyncMock()
    pool = make_pool(conn)
    cache = MagicMock()
    await remove_from_cache(pool, 123, "Steve", cache=cache)
    cache.delete.assert_called_once_with("whitelist_usernames:123")


@pytest.mark.asyncio
async def test_remove_from_cache_exception_logs(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.whitelist_cache")
    conn = AsyncMock()
    conn.execute.side_effect = Exception("DB error")
    pool = make_pool(conn)

    await remove_from_cache(pool, 123, "Steve")
    assert "Failed to remove from whitelist cache" in caplog.text


@pytest.mark.asyncio
async def test_sync_from_rcon_success():
    conn = AsyncMock()
    conn.executemany = AsyncMock()
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 2 whitelisted players: Alice, Bob"

    result = await sync_from_rcon(pool, 123, rcon)
    assert result is True
    conn.execute.assert_awaited_once()
    conn.executemany.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_from_rcon_invalidates_cache():
    conn = AsyncMock()
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 1 whitelisted player: Alice"
    cache = MagicMock()
    result = await sync_from_rcon(pool, 123, rcon, cache=cache)
    assert result is True
    cache.delete.assert_called_once_with("whitelist_usernames:123")


@pytest.mark.asyncio
async def test_sync_from_rcon_empty_list():
    conn = AsyncMock()
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 0 whitelisted players: "

    result = await sync_from_rcon(pool, 123, rcon)
    assert result is True
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_sync_from_rcon_exception_returns_false(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.whitelist_cache")
    conn = AsyncMock()
    conn.execute.side_effect = Exception("DB error")
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 1 whitelisted player: Alice"

    result = await sync_from_rcon(pool, 123, rcon)
    assert result is False
    assert "Failed to sync whitelist from RCON" in caplog.text


@pytest.mark.asyncio
async def test_sync_from_rcon_rcon_fails():
    pool = make_pool(AsyncMock())
    rcon = AsyncMock()
    rcon.whitelist_list.side_effect = Exception("RCON failed")

    result = await sync_from_rcon(pool, 123, rcon)
    assert result is False


@pytest.mark.asyncio
async def test_sync_from_rcon_with_fetch_uuid():
    conn = AsyncMock()
    conn.executemany = AsyncMock()
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 1 whitelisted player: Steve"

    async def fetch_uuid(username):
        if username == "Steve":
            return ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")
        return None

    result = await sync_from_rcon(pool, 123, rcon, fetch_uuid=fetch_uuid)
    assert result is True
    conn.execute.assert_awaited_once()
    conn.executemany.assert_awaited_once()
    rows = conn.executemany.call_args.args[1]
    assert any(row[2] == "069a79f4-44e9-4726-a5be-fca90e38aaf5" for row in rows)


@pytest.mark.asyncio
async def test_sync_from_rcon_fetch_uuid_returns_none_and_raises(caplog):
    caplog.set_level(logging.DEBUG, logger="bot.utils.whitelist_cache")
    conn = AsyncMock()
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 3 whitelisted players: Steve, Fail, Bob"

    async def fetch_uuid(username):
        if username == "Steve":
            return ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")
        if username == "Fail":
            raise ValueError("API error")
        return None  # Bob

    result = await sync_from_rcon(pool, 123, rcon, fetch_uuid=fetch_uuid)
    assert result is True
    assert "Could not fetch UUID" in caplog.text


@pytest.mark.asyncio
async def test_sync_from_rcon_with_batch_fetch():
    conn = AsyncMock()
    conn.executemany = AsyncMock()
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 2 whitelisted players: Steve, Alex"

    async def batch_fetch(usernames):
        return {
            "steve": ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve"),
            "alex": ("11111111-2222-3333-4444-555555555555", "Alex"),
        }

    result = await sync_from_rcon(pool, 123, rcon, batch_fetch=batch_fetch)
    assert result is True
    conn.execute.assert_awaited_once()
    conn.executemany.assert_awaited_once()
    rows = conn.executemany.call_args.args[1]
    uuids = {row[2] for row in rows}
    assert "069a79f4-44e9-4726-a5be-fca90e38aaf5" in uuids
    assert "11111111-2222-3333-4444-555555555555" in uuids


@pytest.mark.asyncio
async def test_sync_from_rcon_batch_fetch_exception(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.whitelist_cache")
    conn = AsyncMock()
    pool = make_pool(conn)
    rcon = AsyncMock()
    rcon.whitelist_list.return_value = "There are 1 whitelisted player: Steve"

    async def batch_fetch(usernames):
        raise ValueError("API error")

    result = await sync_from_rcon(pool, 123, rcon, batch_fetch=batch_fetch)
    assert result is True
    assert "Batch UUID fetch failed" in caplog.text


@pytest.mark.asyncio
async def test_get_cache_entry_success():
    conn = AsyncMock()
    u = uuid.UUID("069a79f4-44e9-4726-a5be-fca90e38aaf5")
    conn.fetchrow = AsyncMock(return_value={"username": "Steve", "minecraft_uuid": u})
    pool = make_pool(conn)

    result = await get_cache_entry(pool, 1, "Steve")
    assert result is not None
    assert result["username"] == "Steve"
    assert result["minecraft_uuid"] == "069a79f4-44e9-4726-a5be-fca90e38aaf5"


@pytest.mark.asyncio
async def test_get_cache_entry_not_found():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = make_pool(conn)
    assert await get_cache_entry(pool, 1, "Nobody") is None


@pytest.mark.asyncio
async def test_get_cache_entry_row_without_uuid():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"username": "Steve", "minecraft_uuid": None})
    pool = make_pool(conn)
    result = await get_cache_entry(pool, 1, "Steve")
    assert result["minecraft_uuid"] is None


@pytest.mark.asyncio
async def test_get_cache_entry_exception(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.whitelist_cache")
    pool = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = ctx
    assert await get_cache_entry(pool, 1, "x") is None
    assert "Failed to fetch whitelist cache entry" in caplog.text


@pytest.mark.asyncio
async def test_reconcile_renames_row_when_uuid_maps_to_new_name():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"username": "Old", "minecraft_uuid": uuid.uuid4()}])
    conn.execute = AsyncMock()
    pool = make_pool(conn)
    with patch(
        "bot.utils.whitelist_cache.get_profile_by_uuid",
        new_callable=AsyncMock,
        return_value=("069a79f4-44e9-4726-a5be-fca90e38aaf5", "New"),
    ):
        out = await reconcile_whitelist_cache(pool, 99)
    assert any("Old → New" in x for x in out["updated"])
    assert conn.execute.await_count >= 2


@pytest.mark.asyncio
async def test_reconcile_prunes_when_username_has_no_mojang_profile():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"username": "Ghost", "minecraft_uuid": None}])
    conn.execute = AsyncMock()
    pool = make_pool(conn)
    with patch("bot.utils.whitelist_cache.get_profile", new_callable=AsyncMock, return_value=None):
        out = await reconcile_whitelist_cache(pool, 3)
    assert "Ghost" in out["pruned"]
    conn.execute.assert_awaited()


@pytest.mark.asyncio
async def test_reconcile_backfills_uuid_when_name_valid():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"username": "Steve", "minecraft_uuid": None}])
    conn.execute = AsyncMock()
    pool = make_pool(conn)
    with patch(
        "bot.utils.whitelist_cache.get_profile",
        new_callable=AsyncMock,
        return_value=("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve"),
    ):
        out = await reconcile_whitelist_cache(pool, 3)
    assert "Steve" in out["uuid_filled"]
    conn.execute.assert_awaited()


@pytest.mark.asyncio
async def test_reconcile_uuid_row_unchanged_when_mojang_name_matches():
    conn = AsyncMock()
    u = uuid.uuid4()
    conn.fetch = AsyncMock(return_value=[{"username": "Steve", "minecraft_uuid": u}])
    pool = make_pool(conn)
    with patch(
        "bot.utils.whitelist_cache.get_profile_by_uuid",
        new_callable=AsyncMock,
        return_value=("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve"),
    ):
        out = await reconcile_whitelist_cache(pool, 3)
    assert out == {"updated": [], "uuid_filled": [], "pruned": []}


@pytest.mark.asyncio
async def test_reconcile_uuid_row_skips_when_session_returns_no_profile():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"username": "Steve", "minecraft_uuid": uuid.uuid4()}])
    pool = make_pool(conn)
    with patch(
        "bot.utils.whitelist_cache.get_profile_by_uuid",
        new_callable=AsyncMock,
        return_value=None,
    ):
        out = await reconcile_whitelist_cache(pool, 3)
    assert out == {"updated": [], "uuid_filled": [], "pruned": []}


@pytest.mark.asyncio
async def test_reconcile_no_uuid_row_renamed_via_mojang_lookup():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"username": "oldn", "minecraft_uuid": None}])
    conn.execute = AsyncMock()
    pool = make_pool(conn)
    with patch(
        "bot.utils.whitelist_cache.get_profile",
        new_callable=AsyncMock,
        return_value=("069a79f4-44e9-4726-a5be-fca90e38aaf5", "NewN"),
    ):
        out = await reconcile_whitelist_cache(pool, 3)
    assert any("oldn → NewN" in x for x in out["updated"])


@pytest.mark.asyncio
async def test_reconcile_logs_on_fetch_failure(caplog):
    caplog.set_level(logging.WARNING, logger="bot.utils.whitelist_cache")
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=RuntimeError("fetch failed"))
    pool = make_pool(conn)
    out = await reconcile_whitelist_cache(pool, 3)
    assert out == {"updated": [], "uuid_filled": [], "pruned": []}
    assert "reconcile failed" in caplog.text
