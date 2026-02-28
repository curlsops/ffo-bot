"""Reaction event handler."""

import logging
from typing import Optional

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ReactionHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
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
            await member.add_roles(role, reason="Reaction role")
        except discord.HTTPException as e:
            logger.error(f"Failed to assign role: {e}")
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_assignment").inc()

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
            logger.error(f"Failed to remove role: {e}")
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_removal").inc()

    async def _get_reaction_role(
        self, server_id: int, message_id: int, emoji: str
    ) -> Optional[int]:
        try:
            async with self.bot.db_pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT role_id FROM reaction_roles WHERE server_id = $1 AND message_id = $2 AND emoji = $3 AND is_active = true",
                    server_id,
                    message_id,
                    emoji,
                )
        except Exception as e:
            logger.error(f"Error fetching reaction role: {e}")
            return None


async def setup(bot):
    await bot.add_cog(ReactionHandler(bot))
