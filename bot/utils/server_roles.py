"""Server role configuration: map Discord roles to bot permission levels."""

import logging
from typing import TYPE_CHECKING

from bot.utils.config_repair import repair_servers_config
from config.constants import Role

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)

CACHE_KEY = "server_roles:{server_id}"
CACHE_TTL = 300

ROLE_KEYS = {
    Role.SUPER_ADMIN: "super_admin_role_id",
    Role.ADMIN: "admin_role_id",
    Role.MODERATOR: "moderator_role_id",
}


def _extract_role_ids_from_config(cfg) -> dict[Role, int]:
    if not isinstance(cfg, dict):
        return {}
    result = {}
    for role, key in ROLE_KEYS.items():
        if val := cfg.get(key):
            try:
                result[role] = int(val)
            except (TypeError, ValueError):
                pass
    return result


async def get_server_role_ids(
    db_pool, server_id: int, cache: "InMemoryCache | None" = None
) -> dict[Role, int]:
    """Return configured Discord role IDs for each bot role. Empty dict if none."""
    cache_key = CACHE_KEY.format(server_id=server_id)
    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        cfg = row["config"] if row else None
        repaired = repair_servers_config(cfg) if cfg is not None else None
        result = _extract_role_ids_from_config(repaired) if repaired else {}
        if cache:
            cache.set(cache_key, result, ttl=CACHE_TTL)
        return result
    except Exception as e:
        logger.warning("Failed to get server role config: %s", e)
        return {}


async def set_server_role(
    db_pool,
    server_id: int,
    role: Role,
    discord_role_id: int | None,
    cache: "InMemoryCache | None" = None,
    server_name: str | None = None,
) -> bool:
    """Set or clear a Discord role mapping for a bot role."""
    key = ROLE_KEYS.get(role)
    if not key:
        return False
    try:
        async with db_pool.acquire() as conn:
            if discord_role_id is not None:
                merge = {key: discord_role_id}
                await conn.execute(
                    """
                    INSERT INTO servers (server_id, server_name, config)
                    VALUES ($1, $2, $3::jsonb)
                    ON CONFLICT (server_id) DO UPDATE
                    SET config = COALESCE(servers.config, '{}'::jsonb) || EXCLUDED.config,
                        server_name = COALESCE(NULLIF(EXCLUDED.server_name, 'Unknown'), servers.server_name),
                        updated_at = NOW()
                    """,
                    server_id,
                    server_name or "Unknown",
                    merge,
                )
            else:
                await conn.execute(
                    "UPDATE servers SET config = config - $1, updated_at = NOW() WHERE server_id = $2",
                    key,
                    server_id,
                )
        if cache:
            cache.delete(CACHE_KEY.format(server_id=server_id))
        return True
    except Exception:
        logger.exception("Failed to set server role %s", role.value)
        return False
