import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.pagination import ListPaginatedView
from config.constants import Role

logger = logging.getLogger(__name__)

MESSAGE_LINK_RE = re.compile(r"discord\.com/channels/(\d+)/(\d+)/(\d+)")


def _invalidate_reaction_role_cache(cache, server_id: int, message_id: int, emoji: str) -> None:
    if cache:
        cache.delete(f"reaction_role:{server_id}:{message_id}:{emoji}")
        cache.delete(f"reactionrole_list:{server_id}")


def _parse_message_ref(s: str, guild_id: int, channel_id: int) -> tuple[int, int] | None:
    s = s.strip()
    m = MESSAGE_LINK_RE.search(s)
    if m:
        return int(m.group(2)), int(m.group(3))
    if s.isdigit():
        return channel_id, int(s)
    return None


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class ReactionRoleGroup(app_commands.Group):
    """Reaction role management."""

    def __init__(self, cog: "ReactionRoleCommands"):
        super().__init__(name="reactionrole", description="Reaction role management")
        self.cog = cog

    @app_commands.command(name="add", description="Add a reaction role (Admin only)")
    @app_commands.describe(
        message="Message link or ID (use right-click → Copy Message Link)",
        emoji="Emoji to react with",
        role="Role to assign when users react",
    )
    async def add_cmd(
        self,
        interaction: discord.Interaction,
        message: str,
        emoji: str,
        role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "reactionrole add"):
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
            channel = self.cog.bot.get_channel(channel_id)
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

            async with self.cog.bot.db_pool.acquire() as conn:
                existing = await conn.fetchval(
                    "SELECT id FROM reaction_roles WHERE server_id = $1 AND message_id = $2 AND emoji = $3 AND is_active = true LIMIT 1",
                    interaction.guild_id,
                    message_id,
                    str(emoji),
                )
                if existing:
                    await conn.execute(
                        "UPDATE reaction_roles SET role_id = $1, updated_at = NOW() WHERE id = $2",
                        role.id,
                        existing,
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO reaction_roles (server_id, message_id, channel_id, emoji, role_id, created_by)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        interaction.guild_id,
                        message_id,
                        channel_id,
                        str(emoji),
                        role.id,
                        interaction.user.id,
                    )

            _invalidate_reaction_role_cache(
                self.cog.bot.cache, interaction.guild_id, message_id, str(emoji)
            )
            await interaction.followup.send(
                f"Reaction role added: {emoji} → {role.mention}",
                ephemeral=True,
            )
        except discord.NotFound:
            await interaction.followup.send("Message not found.", ephemeral=True)
        except Exception as e:
            logger.error("reactionrole_add error: %s", e, exc_info=True)
            await interaction.followup.send("Error adding reaction role.", ephemeral=True)

    @app_commands.command(name="remove", description="Remove a reaction role (Admin only)")
    @app_commands.describe(
        message="Message link or ID",
        emoji="Emoji to remove",
    )
    async def remove_cmd(
        self,
        interaction: discord.Interaction,
        message: str,
        emoji: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "reactionrole remove"):
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

            async with self.cog.bot.db_pool.acquire() as conn:
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

            _invalidate_reaction_role_cache(
                self.cog.bot.cache, interaction.guild_id, message_id, str(emoji)
            )
            channel = self.cog.bot.get_channel(channel_id)
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
            logger.error("reactionrole_remove error: %s", e, exc_info=True)
            await interaction.followup.send(
                "Error removing reaction role.",
                ephemeral=True,
            )

    @app_commands.command(name="list", description="List all reaction roles (Admin only)")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "reactionrole list"):
            return

        try:
            cache_key = f"reactionrole_list:{interaction.guild_id}"
            rows = self.cog.bot.cache.get(cache_key) if self.cog.bot.cache else None
            if rows is None:
                async with self.cog.bot.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT message_id, channel_id, emoji, role_id
                        FROM reaction_roles
                        WHERE server_id = $1 AND is_active = true
                        ORDER BY channel_id, message_id
                        """,
                        interaction.guild_id,
                    )
                rows = [dict(r) for r in rows]
                if self.cog.bot.cache:
                    self.cog.bot.cache.set(cache_key, rows, ttl=300)

            if not rows:
                await interaction.followup.send(
                    "No reaction roles configured.",
                    ephemeral=True,
                )
                return

            guild_id = interaction.guild_id

            def fmt(r):
                return (
                    f"• [msg](https://discord.com/channels/{guild_id}/{r['channel_id']}/{r['message_id']}) "
                    f"{r['emoji']} → <@&{r['role_id']}>"
                )

            view = ListPaginatedView(rows, "**Reaction Roles:**", fmt)
            await interaction.followup.send(
                view._format_page(),
                view=view,
                ephemeral=True,
            )
        except Exception as e:
            logger.error("reactionrole_list error: %s", e, exc_info=True)
            await interaction.followup.send(
                "Error listing reaction roles.",
                ephemeral=True,
            )


class ReactionRoleCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reactionrole_group = ReactionRoleGroup(self)

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

    async def cog_load(self):
        self.bot.tree.add_command(self.reactionrole_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.reactionrole_group.name)


async def setup(bot):
    await bot.add_cog(ReactionRoleCommands(bot))
