"""Whitelist cache - sync from RCON, store in DB for autocomplete."""

import logging
from typing import TYPE_CHECKING, Optional

from bot.services.minecraft_rcon import parse_whitelist_list_response

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)

CACHE_KEY_WHITELIST = "whitelist_usernames:{server_id}"


def _invalidate_whitelist_cache(cache: Optional["InMemoryCache"], server_id: int) -> None:
    if cache:
        cache.delete(CACHE_KEY_WHITELIST.format(server_id=server_id))


async def get_cached_usernames(
    db_pool, server_id: int, cache: Optional["InMemoryCache"] = None
) -> list[str]:
    if cache:
        cached = cache.get(CACHE_KEY_WHITELIST.format(server_id=server_id))
        if cached is not None:
            return cached
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT username FROM whitelist_cache WHERE server_id = $1 ORDER BY username",
                server_id,
            )
        result = [r["username"] for r in rows]
        if cache:
            cache.set(CACHE_KEY_WHITELIST.format(server_id=server_id), result, ttl=300)
        return result
    except Exception as e:
        logger.warning("Failed to get whitelist cache: %s", e)
        return []


async def add_to_cache(
    db_pool,
    server_id: int,
    username: str,
    added_by: Optional[int] = None,
    minecraft_uuid: Optional[str] = None,
    cache: Optional["InMemoryCache"] = None,
) -> None:
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO whitelist_cache (server_id, username, added_by, minecraft_uuid)
                VALUES ($1, $2, $3, $4::uuid)
                ON CONFLICT (server_id, username) DO UPDATE
                SET added_by = EXCLUDED.added_by, added_at = NOW(),
                    minecraft_uuid = COALESCE(EXCLUDED.minecraft_uuid, whitelist_cache.minecraft_uuid)
                """,
                server_id,
                username,
                added_by,
                minecraft_uuid,
            )
        _invalidate_whitelist_cache(cache, server_id)
    except Exception as e:
        logger.warning("Failed to add to whitelist cache: %s", e)


async def remove_from_cache(
    db_pool, server_id: int, username: str, cache: Optional["InMemoryCache"] = None
) -> None:
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM whitelist_cache WHERE server_id = $1 AND username = $2",
                server_id,
                username,
            )
        _invalidate_whitelist_cache(cache, server_id)
    except Exception as e:
        logger.warning("Failed to remove from whitelist cache: %s", e)


async def sync_from_rcon(
    db_pool,
    server_id: int,
    rcon_client,
    fetch_uuid=None,
    batch_fetch=None,
    cache: Optional["InMemoryCache"] = None,
) -> bool:
    """Sync whitelist from RCON to database.

    Args:
        db_pool: Database connection pool
        server_id: Discord server ID
        rcon_client: RCON client instance
        fetch_uuid: Optional single-username lookup function (deprecated, use batch_fetch)
        batch_fetch: Optional batch lookup function (usernames) -> {lowercase_name: (uuid, name)}
    """
    try:
        resp = await rcon_client.whitelist_list()
        usernames = parse_whitelist_list_response(resp)

        uuid_map: dict[str, str] = {}
        if batch_fetch:
            try:
                profiles = await batch_fetch(usernames)
                uuid_map = {name: profile[0] for name, profile in profiles.items()}
                logger.debug("Batch fetched %d/%d UUIDs", len(uuid_map), len(usernames))
            except Exception as e:
                logger.warning("Batch UUID fetch failed: %s", e)
        elif fetch_uuid:
            for username in usernames:
                try:
                    profile = await fetch_uuid(username)
                    if profile:
                        uuid_map[username.lower()] = profile[0]
                except Exception as e:
                    logger.debug("Could not fetch UUID for %s: %s", username, e)

        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM whitelist_cache WHERE server_id = $1", server_id)
            for username in usernames:
                uuid_val = uuid_map.get(username.lower())
                await conn.execute(
                    """
                    INSERT INTO whitelist_cache (server_id, username, minecraft_uuid)
                    VALUES ($1, $2, $3::uuid)
                    """,
                    server_id,
                    username,
                    uuid_val,
                )
        _invalidate_whitelist_cache(cache, server_id)
        return True
    except Exception as e:
        logger.warning("Failed to sync whitelist from RCON: %s", e)
        return False
