import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

PRIVACY_OPERATION_CHOICES = [
    app_commands.Choice(name="Opt in", value="optin"),
    app_commands.Choice(name="Opt out", value="optout"),
]


def _privacy_command(cog: "PrivacyCommands"):
    @app_commands.command(
        name="privacy",
        description="Privacy and message tracking preferences.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(operation="Opt in or opt out of message tracking")
    @app_commands.choices(operation=PRIVACY_OPERATION_CHOICES)
    async def privacy_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if operation.value == "optout":
                async with cog.bot.db_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO user_preferences (server_id, user_id, message_tracking_opt_out, opted_out_at) VALUES ($1, $2, true, NOW()) ON CONFLICT (server_id, user_id) DO UPDATE SET message_tracking_opt_out = true, opted_out_at = NOW()",
                        interaction.guild_id,
                        interaction.user.id,
                    )
                    await conn.execute(
                        "DELETE FROM message_metadata WHERE server_id = $1 AND user_id = $2",
                        interaction.guild_id,
                        interaction.user.id,
                    )
                await interaction.followup.send(
                    "✅ Opted out. Your message history has been deleted.",
                    ephemeral=True,
                )
            else:
                async with cog.bot.db_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO user_preferences (server_id, user_id, message_tracking_opt_out) VALUES ($1, $2, false) ON CONFLICT (server_id, user_id) DO UPDATE SET message_tracking_opt_out = false, opted_out_at = NULL",
                        interaction.guild_id,
                        interaction.user.id,
                    )
                await interaction.followup.send(
                    "✅ Opted back in to message tracking.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error("privacy %s error: %s", operation.value, e, exc_info=True)
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    return privacy_cmd


class PrivacyCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.privacy_cmd = _privacy_command(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.privacy_cmd)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.privacy_cmd.name)


async def setup(bot):
    await bot.add_cog(PrivacyCommands(bot))
