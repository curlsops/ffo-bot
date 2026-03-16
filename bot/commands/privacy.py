import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import execute_command
from bot.utils.user_preferences import invalidate_opt_out_cache

if TYPE_CHECKING:
    from bot.client import FFOBot

logger = logging.getLogger(__name__)

PRIVACY_OPERATION_CHOICES = [
    app_commands.Choice(name="Opt in", value="optin"),
    app_commands.Choice(name="Opt out", value="optout"),
]

_PRIVACY_OPT_OUT_SQL = (
    "INSERT INTO user_preferences "
    "(server_id, user_id, message_tracking_opt_out, opted_out_at) "
    "VALUES ($1, $2, true, NOW()) "
    "ON CONFLICT (server_id, user_id) DO UPDATE "
    "SET message_tracking_opt_out = true, opted_out_at = NOW()"
)
_PRIVACY_OPT_IN_SQL = (
    "INSERT INTO user_preferences (server_id, user_id, message_tracking_opt_out) "
    "VALUES ($1, $2, false) "
    "ON CONFLICT (server_id, user_id) DO UPDATE "
    "SET message_tracking_opt_out = false, opted_out_at = NULL"
)
_DELETE_USER_MESSAGE_HISTORY_SQL = (
    "DELETE FROM message_metadata WHERE server_id = $1 AND user_id = $2"
)


def _privacy_command(cog: "PrivacyCommands"):
    @app_commands.command(
        name="privacy",
        description="Privacy and message tracking preferences.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(operation="Opt in or opt out of message tracking")
    @app_commands.choices(operation=PRIVACY_OPERATION_CHOICES)
    @execute_command(
        error_message="An error occurred.",
        logger=logger,
        log_prefix="privacy command error",
    )
    async def privacy_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        msg = await cog._apply_privacy_operation(interaction, operation.value)
        await interaction.followup.send(msg, ephemeral=True)

    return privacy_cmd


class PrivacyCommands(commands.Cog):
    def __init__(self, bot: "FFOBot"):
        self.bot = bot
        self.privacy_cmd = _privacy_command(self)

    async def _set_opt_out(self, guild_id: int, user_id: int) -> None:
        assert self.bot.db_pool is not None
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(_PRIVACY_OPT_OUT_SQL, guild_id, user_id)
            await conn.execute(_DELETE_USER_MESSAGE_HISTORY_SQL, guild_id, user_id)

    async def _set_opt_in(self, guild_id: int, user_id: int) -> None:
        assert self.bot.db_pool is not None
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(_PRIVACY_OPT_IN_SQL, guild_id, user_id)

    def _invalidate_cache(self, guild_id: int, user_id: int) -> None:
        invalidate_opt_out_cache(self.bot.cache, guild_id, user_id)

    async def _apply_privacy_operation(
        self,
        interaction: discord.Interaction,
        operation: str,
    ) -> str:
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        assert guild_id is not None and self.bot.db_pool is not None and self.bot.cache is not None
        if operation == "optout":
            await self._set_opt_out(guild_id, user_id)
            self._invalidate_cache(guild_id, user_id)
            return "✅ Opted out. Your message history has been deleted."

        await self._set_opt_in(guild_id, user_id)
        self._invalidate_cache(guild_id, user_id)
        return "✅ Opted back in to message tracking."

    async def cog_load(self):
        self.bot.tree.add_command(self.privacy_cmd)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.privacy_cmd.name)


async def setup(bot):
    await bot.add_cog(PrivacyCommands(bot))
