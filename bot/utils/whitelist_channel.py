"""Whitelist channel config (servers.config.whitelist_channel_id)."""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def get_whitelist_channel_id(db_pool, server_id: int) -> Optional[int]:
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        if not row or not row["config"]:
            return None
        config = row["config"]
        if not isinstance(config, dict):
            return None
        if channel_id := config.get("whitelist_channel_id"):
            return int(channel_id)
        return None
    except Exception as e:
        logger.warning("Failed to get whitelist channel: %s", e)
        return None


async def set_whitelist_channel(db_pool, server_id: int, channel_id: Optional[int]) -> bool:
    try:
        async with db_pool.acquire() as conn:
            if channel_id:
                await conn.execute(
                    "UPDATE servers SET config = COALESCE(config, '{}'::jsonb) || $1::jsonb, updated_at = NOW() WHERE server_id = $2",
                    json.dumps({"whitelist_channel_id": channel_id}),
                    server_id,
                )
            else:
                await conn.execute(
                    "UPDATE servers SET config = config - 'whitelist_channel_id', updated_at = NOW() WHERE server_id = $1",
                    server_id,
                )
        return True
    except Exception:
        logger.exception("Failed to set whitelist channel")
        return False
