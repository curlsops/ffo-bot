import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from config.constants import Role

if TYPE_CHECKING:
    from discord.ext.commands import Bot

logger = logging.getLogger(__name__)


@dataclass
class PermissionContext:
    server_id: int
    user_id: int
    command_name: Optional[str] = None


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

        self.cache.set(cache_key, has_permission, ttl=60)
        return has_permission

    async def get_user_role(self, server_id: int, user_id: int) -> Optional[Role]:
        cache_key = f"user_role:{server_id}:{user_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

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
        self.cache.set(cache_key, role, ttl=300)
        return role

    async def _log_permission_denial(self, ctx: PermissionContext, required_role: Role):
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log (server_id, user_id, action, target_type, details)
                    VALUES ($1, $2, 'permission_denied', 'command', $3)
                    """,
                    ctx.server_id,
                    ctx.user_id,
                    json.dumps({"command": ctx.command_name, "required_role": required_role.value}),
                )
        except Exception as e:
            logger.error(f"Failed to log permission denial: {e}")

    def invalidate_user_cache(self, server_id: int, user_id: int):
        self.cache.delete(f"user_role:{server_id}:{user_id}")
