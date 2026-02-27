"""Permission checking and authorization."""

import logging
from dataclasses import dataclass
from typing import Optional

from config.constants import Role

logger = logging.getLogger(__name__)


@dataclass
class PermissionContext:
    """Context for permission checks."""

    server_id: int
    user_id: int
    command_name: Optional[str] = None


class PermissionChecker:
    """Authorization enforcement with caching."""

    def __init__(self, db_pool, cache):
        """
        Initialize permission checker.

        Args:
            db_pool: Database connection pool
            cache: In-memory cache
        """
        self.db_pool = db_pool
        self.cache = cache

    async def check_role(self, ctx: PermissionContext, required_role: Role) -> bool:
        """
        Check if user has required role or higher.

        Args:
            ctx: Permission context
            required_role: Required role level

        Returns:
            True if user has sufficient permissions
        """
        user_role = await self.get_user_role(ctx.server_id, ctx.user_id)

        if not user_role:
            logger.debug(f"User {ctx.user_id} has no role in server {ctx.server_id}")
            return False

        # Role hierarchy check
        has_permission = user_role.hierarchy >= required_role.hierarchy

        # Audit log for permission checks on privileged commands
        if not has_permission and required_role in [Role.SUPER_ADMIN, Role.ADMIN]:
            await self._log_permission_denial(ctx, required_role)

        return has_permission

    async def check_command_permission(self, ctx: PermissionContext) -> bool:
        """
        Check if user has permission for specific command.

        Args:
            ctx: Permission context (must include command_name)

        Returns:
            True if user has command permission
        """
        # Super admins always have access
        if await self.check_role(ctx, Role.SUPER_ADMIN):
            return True

        # Check explicit command permission
        cache_key = f"cmd_perm:{ctx.server_id}:{ctx.user_id}:{ctx.command_name}"
        cached = self.cache.get(cache_key)

        if cached is not None:
            return cached

        async with self.db_pool.acquire() as conn:
            has_permission = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM command_permissions
                    WHERE server_id = $1
                    AND user_id = $2
                    AND command_name = $3
                    AND is_active = true
                )
                """,
                ctx.server_id,
                ctx.user_id,
                ctx.command_name,
            )

        # Cache result for 60 seconds
        self.cache.set(cache_key, has_permission, ttl=60)

        return has_permission

    async def get_user_role(self, server_id: int, user_id: int) -> Optional[Role]:
        """
        Get user's highest role in server.

        Args:
            server_id: Discord server ID
            user_id: Discord user ID

        Returns:
            User's role or None
        """
        cache_key = f"user_role:{server_id}:{user_id}"
        cached = self.cache.get(cache_key)

        if cached is not None:
            return cached

        async with self.db_pool.acquire() as conn:
            role_str = await conn.fetchval(
                """
                SELECT role FROM user_permissions
                WHERE server_id = $1 AND user_id = $2 AND is_active = true
                ORDER BY
                    CASE role
                        WHEN 'super_admin' THEN 3
                        WHEN 'admin' THEN 2
                        WHEN 'moderator' THEN 1
                    END DESC
                LIMIT 1
                """,
                server_id,
                user_id,
            )

        role = Role(role_str) if role_str else None

        # Cache for 5 minutes
        self.cache.set(cache_key, role, ttl=300)

        return role

    async def _log_permission_denial(self, ctx: PermissionContext, required_role: Role):
        """
        Log failed permission check for audit.

        Args:
            ctx: Permission context
            required_role: Required role that was not met
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log
                    (server_id, user_id, action, target_type, details)
                    VALUES ($1, $2, 'permission_denied', 'command', $3)
                    """,
                    ctx.server_id,
                    ctx.user_id,
                    {"command": ctx.command_name, "required_role": required_role.value},
                )
        except Exception as e:
            logger.error(f"Failed to log permission denial: {e}")

    def invalidate_user_cache(self, server_id: int, user_id: int):
        """
        Invalidate cached permissions for user.

        Args:
            server_id: Discord server ID
            user_id: Discord user ID
        """
        # Invalidate role cache
        cache_key = f"user_role:{server_id}:{user_id}"
        self.cache.delete(cache_key)

        logger.debug(f"Invalidated permission cache for user {user_id} in server {server_id}")
