import logging

from discord.ext import commands, tasks

from bot.utils.whitelist_cache import reconcile_whitelist_cache

logger = logging.getLogger(__name__)


async def reconcile_all_cached_servers(bot: commands.Bot) -> None:
    pool = getattr(bot, "db_pool", None)
    if pool is None:
        return
    cache = getattr(bot, "cache", None)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT server_id FROM whitelist_cache")
    except Exception as e:
        logger.warning("Whitelist auto-reconcile: could not list cache servers: %s", e)
        return
    for row in rows:
        sid = int(row["server_id"])
        out = await reconcile_whitelist_cache(pool, sid, cache=cache)
        if out["updated"] or out["pruned"] or out["uuid_filled"]:
            logger.info(
                "Whitelist cache auto-reconcile server_id=%s renamed=%d pruned=%d uuid_backfill=%d",
                sid,
                len(out["updated"]),
                len(out["pruned"]),
                len(out["uuid_filled"]),
            )


class WhitelistCacheReconciler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        st = getattr(self.bot, "settings", None)
        if not st or not getattr(st, "feature_minecraft_whitelist", False):
            return
        hours = float(getattr(st, "whitelist_cache_reconcile_interval_hours", 24.0))
        if hours <= 0:
            return
        self.periodic_whitelist_reconcile.change_interval(hours=hours)
        self.periodic_whitelist_reconcile.start()
        logger.info("Whitelist cache auto-reconcile every %.1f hours", hours)

    async def cog_unload(self) -> None:
        self.periodic_whitelist_reconcile.cancel()

    @tasks.loop(hours=24)
    async def periodic_whitelist_reconcile(self) -> None:
        await reconcile_all_cached_servers(self.bot)

    @periodic_whitelist_reconcile.before_loop
    async def before_periodic_whitelist_reconcile(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WhitelistCacheReconciler(bot))
