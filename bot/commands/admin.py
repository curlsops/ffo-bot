import importlib.metadata
import os

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, send_error


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class AdminGroup(app_commands.Group):
    """Admin configuration and tools."""

    def __init__(self, cog: "AdminCommands"):
        super().__init__(name="admin", description="Admin configuration and tools")
        self.cog = cog

    @app_commands.command(name="version", description="Show bot version")
    async def version(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await require_admin(interaction, "admin version", self.cog.bot):
            return
        try:
            ver = importlib.metadata.version("ffo-bot")
        except importlib.metadata.PackageNotFoundError:
            ver = os.environ.get("FFO_BOT_VERSION", "unknown")
        await interaction.followup.send(f"Running **ffo-bot** v{ver}", ephemeral=True)

    @app_commands.command(
        name="notify_channel",
        description="Set channel for admin notifications (giveaway events, etc.)",
    )
    @app_commands.describe(channel="Channel to send notifications to (leave empty to disable)")
    async def notify_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await send_error(interaction, "Server only.")
            return
        if not await require_admin(interaction, "admin notify_channel", self.cog.bot):
            return

        await self.cog.bot._register_server(interaction.guild)
        new_channel_id = channel.id if channel else None
        current_id = await self.cog.bot.notifier.get_notify_channel_id(interaction.guild_id)

        if current_id == new_channel_id:
            if channel:
                await interaction.followup.send(
                    f"Notifications are already set to {channel.mention}."
                )
            else:
                await interaction.followup.send("Notifications are already disabled.")
            return

        if not new_channel_id and current_id:
            notify_ch = await self.cog.bot.notifier.get_notify_channel(interaction.guild_id)
            if notify_ch:
                embed = discord.Embed(
                    title="Notify Channel Changed",
                    description="Notifications disabled.",
                    color=discord.Color.blue(),
                )
                embed.add_field(name="By", value=f"<@{interaction.user.id}>", inline=True)
                try:
                    await notify_ch.send(embed=embed)
                except Exception:
                    pass

        success = await self.cog.bot.notifier.set_notify_channel(
            interaction.guild_id,
            new_channel_id,
        )
        if not success:
            await interaction.followup.send("Failed to update notification channel.")
            return

        if new_channel_id:
            await self.cog.bot.notifier.notify_notify_channel_changed(
                interaction.guild_id, new_channel_id, interaction.user.id
            )
        if channel:
            await interaction.followup.send(f"Notifications will be sent to {channel.mention}")
        else:
            await interaction.followup.send("Notifications disabled.")


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.admin_group = AdminGroup(self)

    @app_commands.command(name="ping", description="Check if bot is responsive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms", ephemeral=True
        )

    async def cog_load(self):
        self.bot.tree.add_command(self.admin_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.admin_group.name)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
