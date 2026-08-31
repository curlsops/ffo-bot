import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, cast

from bot.services.permissions_repository import PermissionsRepository
from bot.utils.db import TRANSIENT_DB_ERRORS
from bot.utils.telemetry import trace_span
from config.constants import Constants, Role

if TYPE_CHECKING:
    from discord.ext.commands import Bot

logger = logging.getLogger(__name__)


@dataclass
class PermissionContext:
    server_id: int
    user_id: int
    command_name: str | None = None


class GrantOutcome(Enum):
    GRANTED = auto()
    ALREADY_GRANTED = auto()
    ERROR = auto()


class RevokeOutcome(Enum):
    REVOKED = auto()
    NOT_FOUND = auto()
    ERROR = auto()


class PermissionChecker:
    def __init__(self, db_pool, cache, bot: "Bot | None" = None):
        self.db_pool = db_pool
        self.cache = cache
        self.bot = bot
        self.repository = PermissionsRepository(db_pool)

    def _is_discord_admin(self, server_id: int, user_id: int) -> bool:
        if not self.bot:
            return False
        guild = self.bot.get_guild(server_id)
        if not guild:
            return False
        member = guild.get_member(user_id)
        if not member:
            return False
        return bool(member.guild_permissions.administrator)

    async def check_role(self, ctx: PermissionContext, required_role: Role) -> bool:
        is_discord_admin = self._is_discord_admin(ctx.server_id, ctx.user_id)
        with trace_span(
            "auth.check_role",
            attributes={
                "discord.guild_id": str(ctx.server_id),
                "discord.user_id": str(ctx.user_id),
                "ffo.required_role": required_role.value,
                "auth.discord_admin_shortcut": is_discord_admin,
            },
        ):
            if is_discord_admin:
                return True

            user_role = await self.get_user_role(ctx.server_id, ctx.user_id)
            if not user_role:
                return False

            has_permission = user_role.hierarchy >= required_role.hierarchy
            if not has_permission and required_role in (Role.SUPER_ADMIN, Role.ADMIN):
                await self._log_permission_denial(ctx, required_role)

            return has_permission

    async def check_command_permission(self, ctx: PermissionContext) -> bool:
        if await self.check_role(ctx, Role.SUPER_ADMIN):
            return True

        cache_key = f"cmd_perm:{ctx.server_id}:{ctx.user_id}:{ctx.command_name}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return bool(cached)

        try:
            has_permission = await self.repository.has_command_permission(
                ctx.server_id, ctx.user_id, ctx.command_name
            )
        except TRANSIENT_DB_ERRORS:
            if self.bot and hasattr(self.bot, "metrics") and self.bot.metrics:
                self.bot.metrics.db_connection_errors.inc()
            return False

        self.cache.set(cache_key, has_permission, ttl=Constants.COMMAND_PERMISSION_CACHE_TTL)
        return bool(has_permission)

    async def get_user_role(self, server_id: int, user_id: int) -> Role | None:
        cache_key = f"user_role:{server_id}:{user_id}"
        with trace_span(
            "auth.get_user_role",
            attributes={
                "discord.guild_id": str(server_id),
                "discord.user_id": str(user_id),
            },
        ) as span:
            cached = self.cache.get(cache_key)
            if cached is not None:
                span.set_attribute("auth.cache_hit", True)
                span.set_attribute("auth.role_source", "cache")
                return cast(Role | None, cached)

            span.set_attribute("auth.cache_hit", False)

            role = None
            role_source = "none"

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
                                role_source = "discord_roles"
                                break

            if role is None:
                try:
                    role_str = await self.repository.fetch_user_role(server_id, user_id)
                    role = Role(role_str) if role_str else None
                    if role is not None:
                        role_source = "db"
                except TRANSIENT_DB_ERRORS:
                    if self.bot and hasattr(self.bot, "metrics") and self.bot.metrics:
                        self.bot.metrics.db_connection_errors.inc()

            span.set_attribute("auth.role_source", role_source)
            self.cache.set(cache_key, role, ttl=Constants.USER_ROLE_CACHE_TTL)
            return role

    async def _log_permission_denial(self, ctx: PermissionContext, required_role: Role):
        try:
            await self.repository.log_permission_denial(
                ctx.server_id,
                ctx.user_id,
                {"command": ctx.command_name, "required_role": required_role.value},
            )
        except TRANSIENT_DB_ERRORS:
            if self.bot and hasattr(self.bot, "metrics") and self.bot.metrics:
                self.bot.metrics.db_connection_errors.inc()
        except Exception as e:
            logger.error("Failed to log permission denial: %s", e)

    def invalidate_user_cache(self, server_id: int, user_id: int):
        self.cache.delete(f"user_role:{server_id}:{user_id}")

    async def list_grants(self, server_id: int) -> list[dict]:
        try:
            return await self.repository.list_active_grants(server_id)
        except TRANSIENT_DB_ERRORS:
            if self.bot and hasattr(self.bot, "metrics") and self.bot.metrics:
                self.bot.metrics.db_connection_errors.inc()
            raise

    async def grant_role(
        self, server_id: int, user_id: int, role: str, granted_by: int
    ) -> GrantOutcome:
        try:
            if await self.repository.find_active_grant(server_id, user_id, role):
                return GrantOutcome.ALREADY_GRANTED
            await self.repository.insert_grant(server_id, user_id, role, granted_by)
        except TRANSIENT_DB_ERRORS:
            if self.bot and hasattr(self.bot, "metrics") and self.bot.metrics:
                self.bot.metrics.db_connection_errors.inc()
            return GrantOutcome.ERROR
        self.invalidate_user_cache(server_id, user_id)
        return GrantOutcome.GRANTED

    async def revoke_role(self, server_id: int, user_id: int, role: str) -> RevokeOutcome:
        try:
            removed = await self.repository.revoke_grant(server_id, user_id, role)
        except TRANSIENT_DB_ERRORS:
            if self.bot and hasattr(self.bot, "metrics") and self.bot.metrics:
                self.bot.metrics.db_connection_errors.inc()
            return RevokeOutcome.ERROR
        if not removed:
            return RevokeOutcome.NOT_FOUND
        self.invalidate_user_cache(server_id, user_id)
        return RevokeOutcome.REVOKED
