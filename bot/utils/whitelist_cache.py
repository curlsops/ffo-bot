"""Whitelist cache - sync from RCON, store in DB for autocomplete."""

import logging
from typing import Optional

from bot.services.minecraft_rcon import parse_whitelist_list_response

logger = logging.getLogger(__name__)


async def get_cached_usernames(db_pool, server_id: int) -> list[str]:
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT username FROM whitelist_cache WHERE server_id = $1 ORDER BY username",
                server_id,
            )
        return [r["username"] for r in rows]
    except Exception as e:
        logger.warning("Failed to get whitelist cache: %s", e)
        return []


async def add_to_cache(
    db_pool,
    server_id: int,
    username: str,
    added_by: Optional[int] = None,
    minecraft_uuid: Optional[str] = None,
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
    except Exception as e:
        logger.warning("Failed to add to whitelist cache: %s", e)


async def remove_from_cache(db_pool, server_id: int, username: str) -> None:
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM whitelist_cache WHERE server_id = $1 AND username = $2",
                server_id,
                username,
            )
    except Exception as e:
        logger.warning("Failed to remove from whitelist cache: %s", e)


async def sync_from_rcon(db_pool, server_id: int, rcon_client, fetch_uuid=None) -> bool:
    try:
        resp = await rcon_client.whitelist_list()
        usernames = parse_whitelist_list_response(resp)
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM whitelist_cache WHERE server_id = $1", server_id)
            for username in usernames:
                uuid_val = None
                if fetch_uuid:
                    try:
                        profile = await fetch_uuid(username)
                        if profile:
                            uuid_val = profile[0]
                    except Exception as e:
                        logger.debug("Could not fetch UUID for %s: %s", username, e)
                await conn.execute(
                    """
                    INSERT INTO whitelist_cache (server_id, username, minecraft_uuid)
                    VALUES ($1, $2, $3::uuid)
                    """,
                    server_id,
                    username,
                    uuid_val,
                )
        return True
    except Exception as e:
        logger.warning("Failed to sync whitelist from RCON: %s", e)
        return False
