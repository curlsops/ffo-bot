import logging

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
    """Minecraft whitelist management."""

    def __init__(self, cog: "WhitelistCommands"):
        super().__init__(name="whitelist", description="Minecraft whitelist management")
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
            self.cog.bot.db_pool, interaction.guild_id, new_channel_id, cache=self.cog.bot.cache
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

    @app_commands.command(name="add", description="Add a player to the Minecraft whitelist (mod+)")
    @app_commands.describe(username="Minecraft username (3-16 chars)")
    @app_commands.autocomplete(username=_whitelist_username_autocomplete)
    async def add_cmd(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        if not await require_mod(interaction, "whitelist add", self.cog.bot):
            return
        if not await require_rcon(interaction, self.cog.bot):
            return

        valid = _validate_username(username)
        if not valid:
            await interaction.followup.send(
                "Invalid username. Must be 3-16 characters, alphanumeric and underscores only.",
                ephemeral=True,
            )
            return

        try:
            resp = await self.cog.bot.minecraft_rcon.whitelist_add(valid)
            profile = await get_profile(valid)
            minecraft_uuid = profile[0] if profile else None
            await add_to_cache(
                self.cog.bot.db_pool,
                interaction.guild_id,
                valid,
                added_by=interaction.user.id,
                minecraft_uuid=minecraft_uuid,
                cache=self.cog.bot.cache,
            )
            await interaction.followup.send(f"Whitelist: {resp}", ephemeral=True)
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist add failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    @app_commands.command(
        name="remove", description="Remove a player from the Minecraft whitelist (mod+)"
    )
    @app_commands.describe(username="Minecraft username")
    @app_commands.autocomplete(username=_whitelist_username_autocomplete)
    async def remove_cmd(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        if not await require_mod(interaction, "whitelist remove", self.cog.bot):
            return
        if not await require_rcon(interaction, self.cog.bot):
            return

        valid = _validate_username(username)
        if not valid:
            await interaction.followup.send(
                "Invalid username. Must be 3-16 characters, alphanumeric and underscores only.",
                ephemeral=True,
            )
            return

        try:
            resp = await self.cog.bot.minecraft_rcon.whitelist_remove(valid)
            await remove_from_cache(
                self.cog.bot.db_pool, interaction.guild_id, valid, cache=self.cog.bot.cache
            )
            await interaction.followup.send(f"Whitelist: {resp}", ephemeral=True)
        except MinecraftRCONError as e:
            logger.warning("RCON whitelist remove failed: %s", e)
            await interaction.followup.send(
                "Could not connect to the Minecraft server. Check RCON configuration.",
                ephemeral=True,
            )

    @app_commands.command(
        name="sync", description="Sync whitelist from Minecraft server to cache (mod+)"
    )
    async def sync_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await require_mod(interaction, "whitelist sync", self.cog.bot):
            return
        if not await require_rcon(interaction, self.cog.bot):
            return
        success = await sync_from_rcon(
            self.cog.bot.db_pool,
            interaction.guild_id,
            self.cog.bot.minecraft_rcon,
            batch_fetch=get_profiles_batch,
            cache=self.cog.bot.cache,
        )
        if success:
            count = len(
                await get_cached_usernames(
                    self.cog.bot.db_pool, interaction.guild_id, cache=self.cog.bot.cache
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

    @app_commands.command(name="list", description="List whitelisted players (mod+)")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await require_mod(interaction, "whitelist list", self.cog.bot):
            return
        if not await require_rcon(interaction, self.cog.bot):
            return

        try:
            resp = await self.cog.bot.minecraft_rcon.whitelist_list()
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


class WhitelistCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.whitelist_group = WhitelistGroup(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.whitelist_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.whitelist_group.name)


async def setup(bot):
    await bot.add_cog(WhitelistCommands(bot))
