import logging
from typing import TYPE_CHECKING

from bot.utils.server_config import get_server_config_channel, invalidate_servers_config

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)


async def get_quotebook_channel_id(
    db_pool, server_id: int, cache: "InMemoryCache | None" = None
) -> int | None:
    return await get_server_config_channel(db_pool, server_id, "quotebook_channel_id", cache)


async def set_quotebook_channel(
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
                    {"quotebook_channel_id": channel_id},
                    server_id,
                )
            else:
                await conn.execute(
                    "UPDATE servers SET config = config - 'quotebook_channel_id', updated_at = NOW() WHERE server_id = $1",
                    server_id,
                )
        invalidate_servers_config(cache, server_id)
        return True
    except Exception:
        logger.exception("Failed to set quotebook channel")
        return False
