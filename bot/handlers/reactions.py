import logging
from typing import Optional

import discord
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.whitelist_cache import add_to_cache
from config.constants import Role

logger = logging.getLogger(__name__)


class ReactionHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if await self._handle_whitelist_reaction(payload):
            return

        role_id = await self._get_reaction_role(
            payload.guild_id, payload.message_id, str(payload.emoji)
        )
        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(role_id) if guild else None

        if not member or not role:
            return

        try:
            await member.add_roles(role, reason="Reaction role")
        except discord.HTTPException as e:
            logger.error("Failed to assign role: %s", e)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_assignment").inc()

    async def _handle_whitelist_reaction(self, payload: discord.RawReactionActionEvent) -> bool:
        if not payload.guild_id or not getattr(
            self.bot.settings, "feature_minecraft_whitelist", False
        ):
            return False

        from bot.commands.whitelist import WHITELIST_APPROVE_EMOJI, WHITELIST_REJECT_EMOJI
        from bot.services.mojang import get_profile

        emoji_str = str(payload.emoji)
        if emoji_str not in (WHITELIST_APPROVE_EMOJI, WHITELIST_REJECT_EMOJI):
            return False

        ctx = PermissionContext(
            server_id=payload.guild_id,
            user_id=payload.user_id,
            command_name="whitelist_approve",
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.MODERATOR):
            return False

        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                DELETE FROM whitelist_pending
                WHERE server_id = $1 AND message_id = $2
                RETURNING username, channel_id, minecraft_uuid
                """,
                payload.guild_id,
                payload.message_id,
            )
        if not row:
            return False

        username = row["username"]
        channel_id = row["channel_id"]
        minecraft_uuid = row.get("minecraft_uuid")
        if minecraft_uuid is None:
            profile = await get_profile(username)
            minecraft_uuid = profile[0] if profile else None

        if emoji_str == WHITELIST_APPROVE_EMOJI and self.bot.minecraft_rcon:
            try:
                resp = await self.bot.minecraft_rcon.whitelist_add(username)
                await add_to_cache(
                    self.bot.db_pool,
                    payload.guild_id,
                    username,
                    added_by=payload.user_id,
                    minecraft_uuid=str(minecraft_uuid) if minecraft_uuid else None,
                    cache=self.bot.cache,
                )
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(
                    channel_id
                )
                if channel:
                    await channel.send(f"✅ **{username}** added to whitelist. {resp}")
            except Exception as e:
                logger.warning("RCON whitelist add on approve failed: %s", e)
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(
                    channel_id
                )
                if channel:
                    await channel.send(f"❌ Failed to add **{username}** to whitelist: {e}")

        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            if channel:
                msg = await channel.fetch_message(payload.message_id)
                await msg.clear_reactions()
        except Exception as e:
            logger.debug("Could not clear whitelist message reactions: %s", e)

        return True

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        role_id = await self._get_reaction_role(
            payload.guild_id, payload.message_id, str(payload.emoji)
        )
        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(role_id) if guild else None

        if not member or not role:
            return

        try:
            await member.remove_roles(role, reason="Reaction role")
        except discord.HTTPException as e:
            logger.error("Failed to remove role: %s", e)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_removal").inc()

    async def _get_reaction_role(
        self, server_id: int, message_id: int, emoji: str
    ) -> Optional[int]:
        cache_key = f"reaction_role:{server_id}:{message_id}:{emoji}"
        cached = self.bot.cache.get(cache_key) if self.bot.cache else None
        if cached is not None:
            return None if cached == -1 else cached
        try:
            async with self.bot.db_pool.acquire() as conn:
                role_id = await conn.fetchval(
                    "SELECT role_id FROM reaction_roles WHERE server_id = $1 AND message_id = $2 AND emoji = $3 AND is_active = true",
                    server_id,
                    message_id,
                    emoji,
                )
            if self.bot.cache:
                self.bot.cache.set(cache_key, role_id if role_id is not None else -1, ttl=300)
            return role_id
        except Exception as e:
            logger.error("Error fetching reaction role: %s", e)
            return None


async def setup(bot):
    await bot.add_cog(ReactionHandler(bot))
