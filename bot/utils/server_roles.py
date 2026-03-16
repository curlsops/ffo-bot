import logging
from typing import TYPE_CHECKING

from bot.utils.server_config import get_servers_config, invalidate_servers_config
from config.constants import Role

if TYPE_CHECKING:
    from bot.cache.memory import InMemoryCache

logger = logging.getLogger(__name__)

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
    cfg = await get_servers_config(db_pool, server_id, cache)
    return _extract_role_ids_from_config(cfg)


async def set_server_role(
    db_pool,
    server_id: int,
    role: Role,
    discord_role_id: int | None,
    cache: "InMemoryCache | None" = None,
    server_name: str | None = None,
) -> bool:
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
        invalidate_servers_config(cache, server_id)
        return True
    except Exception:
        logger.exception("Failed to set server role %s", role.value)
        return False
