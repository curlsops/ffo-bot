from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.tasks.whitelist_cache_reconcile import (
    WhitelistCacheReconciler,
    reconcile_all_cached_servers,
    setup,
)


@pytest.fixture
def bot():
    b = MagicMock()
    b.settings = MagicMock(
        feature_minecraft_whitelist=False, whitelist_cache_reconcile_interval_hours=24.0
    )
    b.wait_until_ready = AsyncMock()
    b.db_pool = MagicMock()
    b.cache = MagicMock()
    return b


@pytest.mark.asyncio
async def test_setup_adds_cog(bot):
    bot.add_cog = AsyncMock()
    await setup(bot)
    bot.add_cog.assert_called_once()
    assert isinstance(bot.add_cog.call_args[0][0], WhitelistCacheReconciler)


@pytest.mark.asyncio
async def test_reconcile_all_cached_servers_no_pool():
    bot = MagicMock()
    bot.db_pool = None
    await reconcile_all_cached_servers(bot)


@pytest.mark.asyncio
async def test_reconcile_all_cached_servers_fetch_fails(caplog):
    caplog.set_level("WARNING")
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=RuntimeError("db"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    bot = MagicMock()
    bot.db_pool = pool
    bot.cache = None
    await reconcile_all_cached_servers(bot)
    assert "could not list cache servers" in caplog.text


@pytest.mark.asyncio
async def test_reconcile_all_cached_servers_runs_per_server(caplog):
    caplog.set_level("INFO")
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"server_id": 1}, {"server_id": 2}])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    bot = MagicMock()
    bot.db_pool = pool
    bot.cache = MagicMock()

    async def fake_reconcile(p, sid, cache=None):
        if sid == 1:
            return {"updated": ["a → b"], "pruned": [], "uuid_filled": []}
        return {"updated": [], "pruned": [], "uuid_filled": []}

    with patch(
        "bot.tasks.whitelist_cache_reconcile.reconcile_whitelist_cache",
        new_callable=AsyncMock,
        side_effect=fake_reconcile,
    ):
        await reconcile_all_cached_servers(bot)
    assert "server_id=1" in caplog.text
    assert "renamed=1" in caplog.text


@pytest.mark.asyncio
async def test_cog_load_skips_when_feature_off(bot):
    cog = WhitelistCacheReconciler(bot)
    with patch.object(cog.periodic_whitelist_reconcile, "change_interval") as ci:
        with patch.object(cog.periodic_whitelist_reconcile, "start") as st:
            await cog.cog_load()
            ci.assert_not_called()
            st.assert_not_called()


@pytest.mark.asyncio
async def test_cog_load_skips_when_interval_zero(bot):
    bot.settings.feature_minecraft_whitelist = True
    bot.settings.whitelist_cache_reconcile_interval_hours = 0
    cog = WhitelistCacheReconciler(bot)
    with patch.object(cog.periodic_whitelist_reconcile, "change_interval") as ci:
        with patch.object(cog.periodic_whitelist_reconcile, "start") as st:
            await cog.cog_load()
            ci.assert_not_called()
            st.assert_not_called()


@pytest.mark.asyncio
async def test_cog_load_starts_when_enabled(bot):
    bot.settings.feature_minecraft_whitelist = True
    bot.settings.whitelist_cache_reconcile_interval_hours = 12
    cog = WhitelistCacheReconciler(bot)
    with patch.object(cog.periodic_whitelist_reconcile, "change_interval") as ci:
        with patch.object(cog.periodic_whitelist_reconcile, "start") as st:
            await cog.cog_load()
            ci.assert_called_once_with(hours=12)
            st.assert_called_once()


@pytest.mark.asyncio
async def test_cog_unload_cancels(bot):
    cog = WhitelistCacheReconciler(bot)
    with patch.object(cog.periodic_whitelist_reconcile, "cancel") as c:
        await cog.cog_unload()
        c.assert_called_once()


@pytest.mark.asyncio
async def test_periodic_whitelist_reconcile_invokes_reconcile_all(bot):
    cog = WhitelistCacheReconciler(bot)
    with patch(
        "bot.tasks.whitelist_cache_reconcile.reconcile_all_cached_servers",
        new_callable=AsyncMock,
    ) as m:
        await cog.periodic_whitelist_reconcile()
        m.assert_awaited_once_with(bot)


@pytest.mark.asyncio
async def test_before_periodic_whitelist_reconcile_waits_ready(bot):
    cog = WhitelistCacheReconciler(bot)
    await cog.periodic_whitelist_reconcile._before_loop(cog)
    bot.wait_until_ready.assert_awaited_once()
