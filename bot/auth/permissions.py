import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot.utils.db import TRANSIENT_DB_ERRORS
from config.constants import Role

if TYPE_CHECKING:
    from discord.ext.commands import Bot

logger = logging.getLogger(__name__)


def _log_audit_failure(e: Exception) -> None:
    logger.error("Failed to log permission denial: %s", e)


@dataclass
class PermissionContext:
    server_id: int
    user_id: int
    command_name: str | None = None


class PermissionChecker:
    def __init__(self, db_pool, cache, bot: "Bot" = None):
        self.db_pool = db_pool
        self.cache = cache
        self.bot = bot

    def _is_discord_admin(self, server_id: int, user_id: int) -> bool:
        if not self.bot:
            return False
        guild = self.bot.get_guild(server_id)
        if not guild:
            return False
        member = guild.get_member(user_id)
        if not member:
            return False
        return member.guild_permissions.administrator

    async def check_role(self, ctx: PermissionContext, required_role: Role) -> bool:
        if self._is_discord_admin(ctx.server_id, ctx.user_id):
            return True

        user_role = await self.get_user_role(ctx.server_id, ctx.user_id)
        if not user_role:
            return False

        has_permission = user_role.hierarchy >= required_role.hierarchy
        if not has_permission and required_role in [Role.SUPER_ADMIN, Role.ADMIN]:
            await self._log_permission_denial(ctx, required_role)

        return has_permission

    async def check_command_permission(self, ctx: PermissionContext) -> bool:
        if await self.check_role(ctx, Role.SUPER_ADMIN):
            return True

        cache_key = f"cmd_perm:{ctx.server_id}:{ctx.user_id}:{ctx.command_name}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            async with self.db_pool.acquire() as conn:
                has_permission = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM command_permissions
                        WHERE server_id = $1 AND user_id = $2 AND command_name = $3 AND is_active = true
                    )
                    """,
                    ctx.server_id,
                    ctx.user_id,
                    ctx.command_name,
                )
        except TRANSIENT_DB_ERRORS:
            return False

        self.cache.set(cache_key, has_permission, ttl=60)
        return has_permission

    async def get_user_role(self, server_id: int, user_id: int) -> Role | None:
        cache_key = f"user_role:{server_id}:{user_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        role = None

        # Check Discord role membership first (server-configured roles)
        if self.bot:
            from bot.utils.server_roles import get_server_role_ids

            role_ids = await get_server_role_ids(self.db_pool, server_id, cache=self.cache)
            if role_ids:
                guild = self.bot.get_guild(server_id)
                member = guild.get_member(user_id) if guild else None
                if member is None and guild:
                    try:
                        member = await guild.fetch_member(user_id)
                    except Exception:
                        pass
                if member:
                    user_role_ids = {r.id for r in member.roles}
                    for r in (Role.SUPER_ADMIN, Role.ADMIN, Role.MODERATOR):
                        if r in role_ids and role_ids[r] in user_role_ids:
                            role = r
                            break

        # Fall back to user_permissions (explicit grants)
        if role is None:
            try:
                async with self.db_pool.acquire() as conn:
                    role_str = await conn.fetchval(
                        """
                        SELECT role FROM user_permissions
                        WHERE server_id = $1 AND user_id = $2 AND is_active = true
                        ORDER BY CASE role WHEN 'super_admin' THEN 3 WHEN 'admin' THEN 2 WHEN 'moderator' THEN 1 END DESC
                        LIMIT 1
                        """,
                        server_id,
                        user_id,
                    )
                role = Role(role_str) if role_str else None
            except TRANSIENT_DB_ERRORS:
                pass

        self.cache.set(cache_key, role, ttl=300)
        return role

    async def _log_permission_denial(self, ctx: PermissionContext, required_role: Role):
        try:
            async with self.db_pool.acquire(timeout=2) as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log (server_id, user_id, action, target_type, details)
                    VALUES ($1, $2, 'permission_denied', 'command', $3)
                    """,
                    ctx.server_id,
                    ctx.user_id,
                    {"command": ctx.command_name, "required_role": required_role.value},
                )
        except TRANSIENT_DB_ERRORS:
            pass
        except Exception as e:
            _log_audit_failure(e)

    def invalidate_user_cache(self, server_id: int, user_id: int):
        self.cache.delete(f"user_role:{server_id}:{user_id}")
