"""Admin commands."""

import discord
from discord import app_commands
from discord.ext import commands


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check if bot is responsive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
