import logging
from typing import TYPE_CHECKING

from bot.utils.config_repair import repair_servers_config
from bot.utils.server_config import get_server_config_channel, invalidate_servers_config

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)


async def get_channel_config(
    db_pool, server_id: int, config_key: str, cache: "InMemoryCache | None" = None
) -> int | None:
    return await get_server_config_channel(db_pool, server_id, config_key, cache)


_ALLOWED_KEYS = frozenset(
    {"whitelist_channel_id", "quotebook_channel_id", "music_voice_channel_id"}
)


async def set_channel_config(
    db_pool,
    server_id: int,
    config_key: str,
    channel_id: int | None,
    cache: "InMemoryCache | None" = None,
) -> bool:
    if config_key not in _ALLOWED_KEYS:
        return False
    try:
        async with db_pool.acquire() as conn:
            if channel_id:
                await conn.execute(
                    """
                    INSERT INTO servers (server_id, server_name, config)
                    VALUES ($1, $2, $3::jsonb)
                    ON CONFLICT (server_id) DO UPDATE
                    SET config = COALESCE(servers.config, '{}'::jsonb) || EXCLUDED.config,
                        updated_at = NOW()
                    """,
                    server_id,
                    "Unknown",
                    {config_key: channel_id},
                )
            else:
                await conn.execute(
                    "UPDATE servers SET config = config - $1, updated_at = NOW() WHERE server_id = $2",
                    config_key,
                    server_id,
                )
        invalidate_servers_config(cache, server_id)
        return True
    except Exception:
        logger.exception("Failed to set %s", config_key)
        return False


async def get_whitelist_channel_id(
    db_pool, server_id: int, cache: "InMemoryCache | None" = None
) -> int | None:
    return await get_channel_config(db_pool, server_id, "whitelist_channel_id", cache)


async def set_whitelist_channel(
    db_pool,
    server_id: int,
    channel_id: int | None,
    cache: "InMemoryCache | None" = None,
) -> bool:
    return await set_channel_config(db_pool, server_id, "whitelist_channel_id", channel_id, cache)


async def get_quotebook_channel_id(
    db_pool, server_id: int, cache: "InMemoryCache | None" = None
) -> int | None:
    return await get_channel_config(db_pool, server_id, "quotebook_channel_id", cache)


async def set_quotebook_channel(
    db_pool,
    server_id: int,
    channel_id: int | None,
    cache: "InMemoryCache | None" = None,
) -> bool:
    return await set_channel_config(db_pool, server_id, "quotebook_channel_id", channel_id, cache)


async def get_music_voice_channel_id(
    db_pool, server_id: int, cache: "InMemoryCache | None" = None
) -> int | None:
    return await get_channel_config(db_pool, server_id, "music_voice_channel_id", cache)


async def set_music_voice_channel(
    db_pool,
    server_id: int,
    channel_id: int | None,
    cache: "InMemoryCache | None" = None,
) -> bool:
    return await set_channel_config(db_pool, server_id, "music_voice_channel_id", channel_id, cache)


async def fetch_music_voice_channel_targets(db_pool) -> list[tuple[int, int]]:
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT server_id, config FROM servers WHERE (config -> 'music_voice_channel_id') IS NOT NULL"
            )
    except Exception:
        logger.exception("Failed to fetch music voice channel targets")
        return []
    out: list[tuple[int, int]] = []
    for r in rows:
        cfg = repair_servers_config(r["config"]) or {}
        raw = cfg.get("music_voice_channel_id")
        if raw is None:
            continue
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        if cid > 0:
            out.append((int(r["server_id"]), cid))
    return out
