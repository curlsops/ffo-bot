"""Reaction event handler with full role assignment."""

import logging
from typing import Optional

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ReactionHandler(commands.Cog):
    """Handle reaction events for reaction roles."""

    def __init__(self, bot):
        """
        Initialize reaction handler.

        Args:
            bot: Bot instance
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        Handle reaction added event.

        Args:
            payload: Reaction event payload
        """
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        logger.debug(f"Reaction added: {payload.emoji} by {payload.user_id}")

        # Check if this is a reaction role message
        role_id = await self._get_reaction_role(
            payload.guild_id, payload.message_id, str(payload.emoji)
        )

        if not role_id:
            return

        # Assign role
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        role = guild.get_role(role_id)
        if not role:
            logger.warning(f"Role {role_id} not found in guild {guild.id}")
            return

        try:
            await member.add_roles(role, reason="Reaction role assignment")
            logger.info(f"Assigned role {role.name} to {member} in {guild.name}")
        except discord.HTTPException as e:
            logger.error(f"Failed to assign role: {e}")
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_assignment").inc()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """
        Handle reaction removed event.

        Args:
            payload: Reaction event payload
        """
        if payload.user_id == self.bot.user.id:
            return

        logger.debug(f"Reaction removed: {payload.emoji} by {payload.user_id}")

        role_id = await self._get_reaction_role(
            payload.guild_id, payload.message_id, str(payload.emoji)
        )

        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        role = guild.get_role(role_id)
        if not role:
            return

        try:
            await member.remove_roles(role, reason="Reaction role removal")
            logger.info(f"Removed role {role.name} from {member} in {guild.name}")
        except discord.HTTPException as e:
            logger.error(f"Failed to remove role: {e}")
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_removal").inc()

    async def _get_reaction_role(
        self, server_id: int, message_id: int, emoji: str
    ) -> Optional[int]:
        """
        Get role ID for reaction.

        Args:
            server_id: Discord server ID
            message_id: Discord message ID
            emoji: Emoji string

        Returns:
            Role ID or None
        """
        try:
            async with self.bot.db_pool.acquire() as conn:
                role_id = await conn.fetchval(
                    """
                    SELECT role_id FROM reaction_roles
                    WHERE server_id = $1
                    AND message_id = $2
                    AND emoji = $3
                    AND is_active = true
                    """,
                    server_id,
                    message_id,
                    emoji,
                )

            return role_id
        except Exception as e:
            logger.error(f"Error fetching reaction role: {e}")
            return None


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(ReactionHandler(bot))
