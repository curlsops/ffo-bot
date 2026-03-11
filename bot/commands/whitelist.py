import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, require_mod, require_rcon
from bot.services.minecraft_rcon import MinecraftRCONError, parse_whitelist_list_response
from bot.services.mojang import get_profile, get_profiles_batch
from bot.utils.pagination import ListPaginatedView
from bot.utils.whitelist_cache import (
    add_to_cache,
    get_cached_usernames,
    remove_from_cache,
    sync_from_rcon,
)
from bot.utils.whitelist_channel import get_whitelist_channel_id, set_whitelist_channel

logger = logging.getLogger(__name__)

WHITELIST_APPROVE_EMOJI = "\u2705"  # ✅
WHITELIST_REJECT_EMOJI = "\u274c"  # ❌

OPERATION_CHOICES = [
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="List", value="list"),
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="Sync", value="sync"),
]


async def _whitelist_username_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    bot = interaction.client
    if not bot.minecraft_rcon:
        return []
    usernames = await get_cached_usernames(bot.db_pool, interaction.guild_id, cache=bot.cache)
    if not usernames and bot.minecraft_rcon._is_configured():
        await sync_from_rcon(
            bot.db_pool,
            interaction.guild_id,
            bot.minecraft_rcon,
            batch_fetch=get_profiles_batch,
            cache=bot.cache,
        )
        usernames = await get_cached_usernames(bot.db_pool, interaction.guild_id, cache=bot.cache)
    cur = current.lower()
    choices = [
        app_commands.Choice(name=u, value=u) for u in usernames if not cur or cur in u.lower()
    ]
    return choices[:25]


def _validate_username(username: str) -> str | None:
    s = username.strip()
    if not (3 <= len(s) <= 16):
        return None
    return s if s.replace("_", "").isalnum() else None


@app_commands.guild_only()
class WhitelistGroup(app_commands.Group):
    """Minecraft whitelist management. Operations: Add, List, Off, On, Remove, Sync."""

    def __init__(self, cog: "WhitelistCommands"):
        super().__init__(
            name="whitelist",
            description="Minecraft whitelist management. Operations: Add, List, Off, On, Remove, Sync.",
        )
        self.cog = cog

    @app_commands.command(name="channel", description="Set channel for whitelist IGN posts (admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to monitor (leave empty to disable)")
    async def channel_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await require_admin(interaction, "whitelist channel", self.cog.bot):
            return

        await self.cog.bot._register_server(interaction.guild)
        new_channel_id = channel.id if channel else None
        current_id = await get_whitelist_channel_id(
            self.cog.bot.db_pool, interaction.guild_id, cache=self.cog.bot.cache
        )

        if current_id == new_channel_id:
            if channel:
                await interaction.followup.send(
                    f"Whitelist channel is already set to {channel.mention}."
                )
            else:
                await interaction.followup.send("Whitelist channel is already disabled.")
            return

        success = await set_whitelist_channel(
            self.cog.bot.db_pool,
            interaction.guild_id,
            new_channel_id,
            cache=self.cog.bot.cache,
        )
        if not success:
            await interaction.followup.send("Failed to update whitelist channel.")
            return

        if channel:
            await interaction.followup.send(
                f"Whitelist channel set to {channel.mention}. "
                "Users should post only their Minecraft IGN (one per message)."
            )
        else:
            await interaction.followup.send("Whitelist channel disabled.")

    @app_commands.command(
        name="run",
        description="Whitelist operations: Add, List, Off, On, Remove, Sync (matches RCON).",
    )
    @app_commands.describe(
        operation="Add, List, Off, On, Remove, Sync",
        channel="Channel for IGN posts (On only, admin)",
        username="Minecraft username (Add/Remove only)",
    )
    @app_commands.choices(operation=OPERATION_CHOICES)
    @app_commands.autocomplete(username=_whitelist_username_autocomplete)
    async def run_cmd(
        self,
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
        channel: discord.TextChannel | None = None,
        username: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        op = operation.value

        if op in ("off", "on"):
            if not await require_admin(interaction, "whitelist", self.cog.bot):
                return
            await self.cog._handle_channel(interaction, op, channel)
            return

        if not await require_mod(interaction, "whitelist", self.cog.bot):
            return
        if not await require_rcon(interaction, self.cog.bot):
            return

        if op == "add":
            await self.cog._handle_add(interaction, username)
        elif op == "list":
            await self.cog._handle_list(interaction)
        elif op == "sync":
            await self.cog._handle_sync(interaction)
        elif op == "remove":
            await self.cog._handle_remove(interaction, username)
        else:
            await interaction.followup.send("Unknown operation.", ephemeral=True)


@app_commands.guild_only()
class WhitelistCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.whitelist_group = WhitelistGroup(self)

    async def _handle_channel(
        self,
        interaction: discord.Interaction,
        op: str,
        channel: Optional[discord.TextChannel],
    ):
        await self.bot._register_server(interaction.guild)
        new_channel_id = channel.id if channel else None
        current_id = await get_whitelist_channel_id(
            self.bot.db_pool, interaction.guild_id, cache=self.bot.cache
        )

        if op == "off":
            new_channel_id = None
        elif op == "on" and not channel:
            await interaction.followup.send(
                "Provide a channel when enabling (e.g. /whitelist run operation:On channel:#whitelist)."
            )
            return

        if current_id == new_channel_id:
            if new_channel_id:
                await interaction.followup.send(
                    f"Whitelist channel is already set to {channel.mention}."
                )
            else:
                await interaction.followup.send("Whitelist channel is already disabled.")
            return

        success = await set_whitelist_channel(
            self.bot.db_pool, interaction.guild_id, new_channel_id, cache=self.bot.cache
        )
        if not success:
            await interaction.followup.send("Failed to update whitelist channel.")
            return

        if new_channel_id:
            await interaction.followup.send(
                f"Whitelist channel set to {channel.mention}. "
                "Users should post only their Minecraft IGN (one per message)."
            )
        else:
            await interaction.followup.send("Whitelist channel disabled.")

    async def _handle_add(self, interaction: discord.Interaction, username: str | None):
        if not username:
            await interaction.followup.send(
                "Username required for Add (e.g. /whitelist run operation:Add username:Steve).",
                ephemeral=True,
            )
            return
        valid = _validate_username(username)
        if not valid:
            await interaction.followup.send(
                "Invalid username. Must be 3-16 characters, alphanumeric and underscores only.",
                ephemeral=True,
            )
            return
        try:
            resp = await self.bot.minecraft_rcon.whitelist_add(valid)
            profile = await get_profile(valid)
            minecraft_uuid = profile[0] if profile else None
            await add_to_cache(
                self.bot.db_pool,
                interaction.guild_id,
                valid,
                added_by=interaction.user.id,
                minecraft_uuid=minecraft_uuid,
                cache=self.bot.cache,
            )
            await interaction.followup.send(f"Whitelist: {resp}", ephemeral=True)
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist add failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    async def _handle_list(self, interaction: discord.Interaction):
        try:
            resp = await self.bot.minecraft_rcon.whitelist_list()
            usernames = parse_whitelist_list_response(resp)
            if not usernames:
                await interaction.followup.send("Whitelist: (empty)", ephemeral=True)
                return

            def fmt(u):
                return f"• {u}"

            view = ListPaginatedView(usernames, "**Whitelisted players:**", fmt)
            await interaction.followup.send(
                view._format_page(),
                view=view,
                ephemeral=True,
            )
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist list failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    async def _handle_sync(self, interaction: discord.Interaction):
        success = await sync_from_rcon(
            self.bot.db_pool,
            interaction.guild_id,
            self.bot.minecraft_rcon,
            batch_fetch=get_profiles_batch,
            cache=self.bot.cache,
        )
        if success:
            count = len(
                await get_cached_usernames(
                    self.bot.db_pool, interaction.guild_id, cache=self.bot.cache
                )
            )
            await interaction.followup.send(
                f"Synced {count} players from Minecraft server.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Failed to sync from Minecraft server.",
                ephemeral=True,
            )

    async def _handle_remove(self, interaction: discord.Interaction, username: str | None):
        if not username:
            await interaction.followup.send(
                "Username required for Remove (e.g. /whitelist run operation:Remove username:Steve).",
                ephemeral=True,
            )
            return
        valid = _validate_username(username)
        if not valid:
            await interaction.followup.send(
                "Invalid username. Must be 3-16 characters, alphanumeric and underscores only.",
                ephemeral=True,
            )
            return
        try:
            resp = await self.bot.minecraft_rcon.whitelist_remove(valid)
            await remove_from_cache(
                self.bot.db_pool, interaction.guild_id, valid, cache=self.bot.cache
            )
            await interaction.followup.send(f"Whitelist: {resp}", ephemeral=True)
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist remove failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    async def cog_load(self):
        self.bot.tree.add_command(self.whitelist_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.whitelist_group.name)


async def setup(bot):
    await bot.add_cog(WhitelistCommands(bot))
