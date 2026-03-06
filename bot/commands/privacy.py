import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class PrivacyGroup(app_commands.Group):

    def __init__(self, cog: "PrivacyCommands"):
        super().__init__(name="privacy", description="Privacy and message tracking preferences")
        self.cog = cog

    @app_commands.command(name="optout", description="Opt out of message tracking")
    async def optout(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.cog.bot.db_pool.acquire() as conn:
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
                "✅ Opted out. Your message history has been deleted.", ephemeral=True
            )
        except Exception as e:
            logger.error("privacy optout error: %s", e, exc_info=True)
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    @app_commands.command(name="optin", description="Opt back in to message tracking")
    async def optin(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO user_preferences (server_id, user_id, message_tracking_opt_out) VALUES ($1, $2, false) ON CONFLICT (server_id, user_id) DO UPDATE SET message_tracking_opt_out = false, opted_out_at = NULL",
                    interaction.guild_id,
                    interaction.user.id,
                )
            await interaction.followup.send("✅ Opted back in to message tracking.", ephemeral=True)
        except Exception as e:
            logger.error("privacy optin error: %s", e, exc_info=True)
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)


class PrivacyCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.privacy_group = PrivacyGroup(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.privacy_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.privacy_group.name)


async def setup(bot):
    await bot.add_cog(PrivacyCommands(bot))
