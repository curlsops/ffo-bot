"""Privacy commands for user opt-out."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class PrivacyCommands(commands.Cog):
    """User privacy commands."""

    def __init__(self, bot):
        """
        Initialize privacy commands.

        Args:
            bot: Bot instance
        """
        self.bot = bot

    @app_commands.command(name="privacy_optout", description="Opt out of message tracking")
    async def privacy_optout(self, interaction: discord.Interaction):
        """
        Allow user to opt out of message tracking.

        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(ephemeral=True)

        try:
            async with self.bot.db_pool.acquire() as conn:
                # Set opt-out preference
                await conn.execute(
                    """
                    INSERT INTO user_preferences (server_id, user_id, message_tracking_opt_out, opted_out_at)
                    VALUES ($1, $2, true, NOW())
                    ON CONFLICT (server_id, user_id) DO UPDATE
                    SET message_tracking_opt_out = true,
                        opted_out_at = NOW()
                    """,
                    interaction.guild_id,
                    interaction.user.id,
                )

                # Delete existing message metadata
                await conn.execute(
                    """
                    DELETE FROM message_metadata
                    WHERE server_id = $1 AND user_id = $2
                    """,
                    interaction.guild_id,
                    interaction.user.id,
                )

            await interaction.followup.send(
                "✅ You have opted out of message tracking.\n"
                "Your message history has been deleted.\n"
                "You can opt back in at any time using `/privacy_optin`.",
                ephemeral=True,
            )

            logger.info(
                f"User {interaction.user.id} opted out of tracking in server {interaction.guild_id}"
            )

        except Exception as e:
            logger.error(f"Error in privacy_optout command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while processing your request.", ephemeral=True
            )

    @app_commands.command(name="privacy_optin", description="Opt back in to message tracking")
    async def privacy_optin(self, interaction: discord.Interaction):
        """
        Allow user to opt back in to message tracking.

        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(ephemeral=True)

        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_preferences (server_id, user_id, message_tracking_opt_out)
                    VALUES ($1, $2, false)
                    ON CONFLICT (server_id, user_id) DO UPDATE
                    SET message_tracking_opt_out = false,
                        opted_out_at = NULL
                    """,
                    interaction.guild_id,
                    interaction.user.id,
                )

            await interaction.followup.send(
                "✅ You have opted back in to message tracking.", ephemeral=True
            )

            logger.info(
                f"User {interaction.user.id} opted in to tracking in server {interaction.guild_id}"
            )

        except Exception as e:
            logger.error(f"Error in privacy_optin command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while processing your request.", ephemeral=True
            )


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(PrivacyCommands(bot))
