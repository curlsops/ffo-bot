"""Admin commands."""

import importlib.metadata
import os

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("Admin required.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="ping", description="Check if bot is responsive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms", ephemeral=True
        )

    @app_commands.command(name="version", description="Show bot version")
    @app_commands.guild_only()
    async def version(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_admin(interaction, "version"):
            return
        try:
            ver = importlib.metadata.version("ffo-bot")
        except importlib.metadata.PackageNotFoundError:
            ver = os.environ.get("FFO_BOT_VERSION", "unknown")
        await interaction.followup.send(f"Running **ffo-bot** v{ver}", ephemeral=True)

    @app_commands.command(
        name="set_notify_channel",
        description="Set channel for admin notifications (giveaway events, etc.)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to send notifications to (leave empty to disable)")
    async def set_notify_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("Server only.")
            return

        if not await self._check_admin(interaction, "set_notify_channel"):
            return

        await self.bot._register_server(interaction.guild)
        new_channel_id = channel.id if channel else None
        current_id = await self.bot.notifier.get_notify_channel_id(interaction.guild_id)

        if current_id == new_channel_id:
            if channel:
                await interaction.followup.send(
                    f"Notifications are already set to {channel.mention}."
                )
            else:
                await interaction.followup.send("Notifications are already disabled.")
            return

        success = await self.bot.notifier.set_notify_channel(
            interaction.guild_id,
            new_channel_id,
        )
        if not success:
            await interaction.followup.send("Failed to update notification channel.")
            return

        if channel:
            await interaction.followup.send(f"Notifications will be sent to {channel.mention}")
        else:
            await interaction.followup.send("Notifications disabled.")


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
