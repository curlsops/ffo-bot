import logging
from typing import TYPE_CHECKING, cast

from bot.utils.config_repair import repair_servers_config
from config.constants import Constants

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)

CACHE_KEY = "servers_config:{server_id}"


def invalidate_servers_config(cache: "InMemoryCache | None", server_id: int) -> None:
    if cache:
        cache.delete(CACHE_KEY.format(server_id=server_id))


async def get_servers_config(db_pool, server_id: int, cache: "InMemoryCache | None" = None) -> dict:
    cache_key = CACHE_KEY.format(server_id=server_id)
    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cast(dict, cached)
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        cfg = repair_servers_config(row["config"]) if row and row["config"] is not None else None
        result = cfg if isinstance(cfg, dict) else {}
        if cache:
            cache.set(cache_key, result, ttl=Constants.CACHE_TTL)
        return result
    except Exception as e:
        logger.warning("Failed to get servers config: %s", e)
        return {}


async def get_server_config_channel(
    db_pool, server_id: int, config_key: str, cache: "InMemoryCache | None" = None
) -> int | None:
    cfg = await get_servers_config(db_pool, server_id, cache)
    val = cfg.get(config_key)
    return int(val) if val else None
