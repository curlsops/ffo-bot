import logging
from typing import TYPE_CHECKING

from bot.utils.config_repair import repair_servers_config
from config.constants import Constants

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)

CACHE_KEY = "whitelist_channel:{server_id}"


async def get_whitelist_channel_id(
    db_pool, server_id: int, cache: "InMemoryCache | None" = None
) -> int | None:
    cache_key = CACHE_KEY.format(server_id=server_id)
    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return None if cached == -1 else cached
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        cfg = repair_servers_config(row["config"]) if row and row["config"] is not None else None
        if not cfg:
            result = None
        elif channel_id := cfg.get("whitelist_channel_id"):
            result = int(channel_id)
        else:
            result = None
        if cache:
            cache.set(cache_key, result if result is not None else -1, ttl=Constants.CACHE_TTL)
        return result
    except Exception as e:
        logger.warning("Failed to get whitelist channel: %s", e)
        return None


async def set_whitelist_channel(
    db_pool,
    server_id: int,
    channel_id: int | None,
    cache: "InMemoryCache | None" = None,
) -> bool:
    try:
        async with db_pool.acquire() as conn:
            if channel_id:
                await conn.execute(
                    "UPDATE servers SET config = COALESCE(config, '{}'::jsonb) || $1::jsonb, updated_at = NOW() WHERE server_id = $2",
                    {"whitelist_channel_id": channel_id},
                    server_id,
                )
            else:
                await conn.execute(
                    "UPDATE servers SET config = config - 'whitelist_channel_id', updated_at = NOW() WHERE server_id = $1",
                    server_id,
                )
        if cache:
            cache.delete(CACHE_KEY.format(server_id=server_id))
        return True
    except Exception:
        logger.exception("Failed to set whitelist channel")
        return False
