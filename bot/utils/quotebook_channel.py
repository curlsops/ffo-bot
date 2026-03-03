"""Quotebook channel: where approved quotes are posted."""

import json
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)

CACHE_KEY = "quotebook_channel:{server_id}"


async def get_quotebook_channel_id(
    db_pool, server_id: int, cache: Optional["InMemoryCache"] = None
) -> Optional[int]:
    cache_key = CACHE_KEY.format(server_id=server_id)
    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return None if cached == -1 else cached
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        if not row or not row["config"]:
            result = None
        elif not isinstance(row["config"], dict):
            result = None
        elif channel_id := row["config"].get("quotebook_channel_id"):
            result = int(channel_id)
        else:
            result = None
        if cache:
            cache.set(cache_key, result if result is not None else -1, ttl=300)
        return result
    except Exception as e:
        logger.warning("Failed to get quotebook channel: %s", e)
        return None


async def set_quotebook_channel(
    db_pool,
    server_id: int,
    channel_id: Optional[int],
    cache: Optional["InMemoryCache"] = None,
) -> bool:
    try:
        async with db_pool.acquire() as conn:
            if channel_id:
                await conn.execute(
                    "UPDATE servers SET config = COALESCE(config, '{}'::jsonb) || $1::jsonb, updated_at = NOW() WHERE server_id = $2",
                    json.dumps({"quotebook_channel_id": channel_id}),
                    server_id,
                )
            else:
                await conn.execute(
                    "UPDATE servers SET config = config - 'quotebook_channel_id', updated_at = NOW() WHERE server_id = $1",
                    server_id,
                )
        if cache:
            cache.delete(CACHE_KEY.format(server_id=server_id))
        return True
    except Exception:
        logger.exception("Failed to set quotebook channel")
        return False
