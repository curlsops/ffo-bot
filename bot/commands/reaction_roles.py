import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, send_error
from bot.utils.pagination import ListPaginatedView
from config.constants import Constants

logger = logging.getLogger(__name__)

MESSAGE_LINK_RE = re.compile(r"discord\.com/channels/(\d+)/(\d+)/(\d+)")

REACTIONROLE_OPERATION_CHOICES = [
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="List", value="list"),
    app_commands.Choice(name="Remove", value="remove"),
]


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


def _reactionrole_command(cog: "ReactionRoleCommands"):
    @app_commands.command(
        name="reactionrole",
        description="Reaction role management. Provide operation.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        operation="Add, List, or Remove a reaction role",
        message="Message link or ID (Add/Remove only)",
        emoji="Emoji (Add/Remove only)",
        role="Role to assign (Add only)",
    )
    @app_commands.choices(operation=REACTIONROLE_OPERATION_CHOICES)
    async def reactionrole_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
        message: str | None = None,
        emoji: str | None = None,
        role: discord.Role | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if operation.value == "list":
            if not await require_admin(interaction, "reactionrole", cog.bot):
                return
            try:
                cache_key = f"reactionrole_list:{interaction.guild_id}"
                rows = cog.bot.cache.get(cache_key) if cog.bot.cache else None
                if rows is None:
                    async with cog.bot.db_pool.acquire() as conn:
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
                    if cog.bot.cache:
                        cog.bot.cache.set(cache_key, rows, ttl=Constants.CACHE_TTL)

                if not rows:
                    await send_error(interaction, "No reaction roles configured.")
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
                await send_error(interaction, "Error listing reaction roles.")
            return

        if operation.value == "add":
            if not await require_admin(interaction, "reactionrole", cog.bot):
                return
            if not message or not emoji or not role:
                await send_error(interaction, "Message, emoji, and role required for Add.")
                return
            try:
                parsed = _parse_message_ref(message, interaction.guild_id, interaction.channel_id)
                if not parsed:
                    await send_error(
                        interaction,
                        "Invalid message. Use a message link or message ID.",
                    )
                    return

                channel_id, message_id = parsed
                channel = cog.bot.get_channel(channel_id)
                if not channel:
                    await send_error(interaction, "Channel not found.")
                    return

                msg = await channel.fetch_message(message_id)

                try:
                    await msg.add_reaction(emoji)
                except discord.HTTPException as e:
                    await send_error(interaction, f"Cannot add that emoji: {e}")
                    return

                async with cog.bot.db_pool.acquire() as conn:
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
                    cog.bot.cache, interaction.guild_id, message_id, str(emoji)
                )
                if cog.bot.notifier:
                    await cog.bot.notifier.notify_reaction_role_setup(
                        interaction.guild_id,
                        "Added",
                        str(emoji),
                        role.id,
                        message_id,
                        channel_id,
                        interaction.user.id,
                    )
                await interaction.followup.send(
                    f"Reaction role added: {emoji} → {role.mention}",
                    ephemeral=True,
                )
            except discord.NotFound:
                await send_error(interaction, "Message not found.")
            except Exception as e:
                logger.error("reactionrole_add error: %s", e, exc_info=True)
                await send_error(interaction, "Error adding reaction role.")
            return

        if operation.value == "remove":
            if not await require_admin(interaction, "reactionrole", cog.bot):
                return
            if not message or not emoji:
                await send_error(interaction, "Message and emoji required for Remove.")
                return
            try:
                parsed = _parse_message_ref(message, interaction.guild_id, interaction.channel_id)
                if not parsed:
                    await send_error(
                        interaction,
                        "Invalid message. Use a message link or message ID.",
                    )
                    return

                channel_id, message_id = parsed

                role_id = None
                async with cog.bot.db_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT role_id FROM reaction_roles
                        WHERE server_id = $1 AND message_id = $2 AND emoji = $3 AND is_active = true
                        """,
                        interaction.guild_id,
                        message_id,
                        str(emoji),
                    )
                    if row:
                        role_id = row["role_id"]
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
                    await send_error(interaction, "Reaction role not found.")
                    return

                _invalidate_reaction_role_cache(
                    cog.bot.cache, interaction.guild_id, message_id, str(emoji)
                )
                if cog.bot.notifier and role_id:
                    await cog.bot.notifier.notify_reaction_role_setup(
                        interaction.guild_id,
                        "Removed",
                        str(emoji),
                        role_id,
                        message_id,
                        channel_id,
                        interaction.user.id,
                    )
                channel = cog.bot.get_channel(channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.clear_reaction(emoji)
                    except (
                        discord.NotFound,
                        discord.HTTPException,
                    ):  # message deleted or reaction gone
                        pass

                await interaction.followup.send(
                    f"Reaction role removed: {emoji}",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error("reactionrole_remove error: %s", e, exc_info=True)
                await send_error(interaction, "Error removing reaction role.")

    return reactionrole_cmd


class ReactionRoleCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reactionrole_cmd = _reactionrole_command(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.reactionrole_cmd)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.reactionrole_cmd.name)


async def setup(bot):
    await bot.add_cog(ReactionRoleCommands(bot))
