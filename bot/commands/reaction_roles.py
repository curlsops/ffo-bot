"""Reaction role management commands."""

import logging
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role

logger = logging.getLogger(__name__)

MESSAGE_LINK_RE = re.compile(r"discord\.com/channels/(\d+)/(\d+)/(\d+)")


def _parse_message_ref(s: str, guild_id: int, channel_id: int) -> Optional[tuple[int, int]]:
    """Parse message link or raw ID. Returns (channel_id, message_id) or None."""
    s = s.strip()
    m = MESSAGE_LINK_RE.search(s)
    if m:
        return int(m.group(2)), int(m.group(3))
    if s.isdigit():
        return channel_id, int(s)
    return None


class ReactionRoleCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        if not interaction.guild:
            await interaction.followup.send("Server only.", ephemeral=True)
            return False
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("Admin required.", ephemeral=True)
            return False
        return True

    @app_commands.command(
        name="reactionrole_add",
        description="Add a reaction role (Admin only)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        message="Message link or ID (use right-click → Copy Message Link)",
        emoji="Emoji to react with",
        role="Role to assign when users react",
    )
    async def reactionrole_add(
        self,
        interaction: discord.Interaction,
        message: str,
        emoji: str,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_admin(interaction, "reactionrole_add"):
            return

        try:
            parsed = _parse_message_ref(message, interaction.guild_id, interaction.channel_id)
            if not parsed:
                await interaction.followup.send(
                    "Invalid message. Use a message link or message ID.",
                    ephemeral=True,
                )
                return

            channel_id, message_id = parsed
            channel = self.bot.get_channel(channel_id)
            if not channel:
                await interaction.followup.send("Channel not found.", ephemeral=True)
                return

            msg = await channel.fetch_message(message_id)

            try:
                await msg.add_reaction(emoji)
            except discord.HTTPException as e:
                await interaction.followup.send(
                    f"Cannot add that emoji: {e}",
                    ephemeral=True,
                )
                return

            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO reaction_roles (server_id, message_id, channel_id, emoji, role_id, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (server_id, message_id, emoji) WHERE (is_active = true)
                    DO UPDATE SET role_id = EXCLUDED.role_id, updated_at = NOW()
                    """,
                    interaction.guild_id,
                    message_id,
                    channel_id,
                    str(emoji),
                    role.id,
                    interaction.user.id,
                )

            await interaction.followup.send(
                f"Reaction role added: {emoji} → {role.mention}",
                ephemeral=True,
            )
        except discord.NotFound:
            await interaction.followup.send("Message not found.", ephemeral=True)
        except Exception as e:
            logger.error(f"reactionrole_add error: {e}", exc_info=True)
            await interaction.followup.send("Error adding reaction role.", ephemeral=True)

    @app_commands.command(
        name="reactionrole_remove",
        description="Remove a reaction role (Admin only)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        message="Message link or ID",
        emoji="Emoji to remove",
    )
    async def reactionrole_remove(
        self,
        interaction: discord.Interaction,
        message: str,
        emoji: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_admin(interaction, "reactionrole_remove"):
            return

        try:
            parsed = _parse_message_ref(message, interaction.guild_id, interaction.channel_id)
            if not parsed:
                await interaction.followup.send(
                    "Invalid message. Use a message link or message ID.",
                    ephemeral=True,
                )
                return

            channel_id, message_id = parsed

            async with self.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE reaction_roles SET is_active = false, updated_at = NOW()
                    WHERE server_id = $1 AND message_id = $2 AND emoji = $3 AND is_active = true
                    """,
                    interaction.guild_id,
                    message_id,
                    str(emoji),
                )

            if "UPDATE 0" in result:
                await interaction.followup.send(
                    "Reaction role not found.",
                    ephemeral=True,
                )
                return

            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.clear_reaction(emoji)
                except (discord.NotFound, discord.HTTPException):
                    pass

            await interaction.followup.send(
                f"Reaction role removed: {emoji}",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"reactionrole_remove error: {e}", exc_info=True)
            await interaction.followup.send(
                "Error removing reaction role.",
                ephemeral=True,
            )

    @app_commands.command(
        name="reactionrole_list",
        description="List all reaction roles (Admin only)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def reactionrole_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_admin(interaction, "reactionrole_list"):
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT message_id, channel_id, emoji, role_id
                    FROM reaction_roles
                    WHERE server_id = $1 AND is_active = true
                    ORDER BY channel_id, message_id
                    """,
                    interaction.guild_id,
                )

            if not rows:
                await interaction.followup.send(
                    "No reaction roles configured.",
                    ephemeral=True,
                )
                return

            lines = []
            for r in rows[:25]:
                lines.append(
                    f"• [msg](https://discord.com/channels/{interaction.guild_id}/{r['channel_id']}/{r['message_id']}) "
                    f"{r['emoji']} → <@&{r['role_id']}>"
                )
            text = "**Reaction Roles:**\n\n" + "\n".join(lines)
            if len(rows) > 25:
                text += f"\n*... and {len(rows) - 25} more*"
            await interaction.followup.send(text, ephemeral=True)
        except Exception as e:
            logger.error(f"reactionrole_list error: {e}", exc_info=True)
            await interaction.followup.send(
                "Error listing reaction roles.",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(ReactionRoleCommands(bot))
