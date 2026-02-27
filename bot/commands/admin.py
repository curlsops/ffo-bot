"""Admin commands."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class AdminCommands(commands.Cog):
    """Administrative commands."""

    def __init__(self, bot):
        """
        Initialize admin commands.

        Args:
            bot: Bot instance
        """
        self.bot = bot

    @app_commands.command(name="ping", description="Check if bot is responsive")
    async def ping(self, interaction: discord.Interaction):
        """
        Simple ping command to test bot responsiveness.

        Args:
            interaction: Discord interaction
        """
        await interaction.response.send_message(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms", ephemeral=True
        )

        logger.info(f"Ping command used by {interaction.user.id}")


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(AdminCommands(bot))
