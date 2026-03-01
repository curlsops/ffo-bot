"""Permission management commands."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role

logger = logging.getLogger(__name__)


class PermissionCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_super_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.SUPER_ADMIN):
            await interaction.followup.send("❌ Super Admin required.", ephemeral=True)
            return False
        return True

    @app_commands.command(
        name="grant_role",
        description="Grant a role to a user (Super Admin only)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="User to grant role to", role="Role to grant")
    @app_commands.choices(
        role=[
            app_commands.Choice(name="Admin", value="admin"),
            app_commands.Choice(name="Moderator", value="moderator"),
        ]
    )
    async def grant_role(self, interaction: discord.Interaction, user: discord.User, role: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self._check_super_admin(interaction, "grant_role"):
                return
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO user_permissions (server_id, user_id, role, granted_by) VALUES ($1, $2, $3, $4) ON CONFLICT (server_id, user_id, role, is_active) WHERE is_active = true DO NOTHING",
                    interaction.guild_id,
                    user.id,
                    role,
                    interaction.user.id,
                )
            self.bot.permission_checker.invalidate_user_cache(interaction.guild_id, user.id)
            await interaction.followup.send(f"✅ Granted {role} to {user.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"grant_role error: {e}", exc_info=True)
            await interaction.followup.send("❌ Error granting role.", ephemeral=True)

    @app_commands.command(
        name="revoke_role",
        description="Revoke a role from a user (Super Admin only)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="User to revoke role from", role="Role to revoke")
    @app_commands.choices(
        role=[
            app_commands.Choice(name="Admin", value="admin"),
            app_commands.Choice(name="Moderator", value="moderator"),
        ]
    )
    async def revoke_role(self, interaction: discord.Interaction, user: discord.User, role: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self._check_super_admin(interaction, "revoke_role"):
                return
            async with self.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE user_permissions SET is_active = false, revoked_at = NOW() WHERE server_id = $1 AND user_id = $2 AND role = $3 AND is_active = true",
                    interaction.guild_id,
                    user.id,
                    role,
                )
            if result == "UPDATE 0":
                await interaction.followup.send(
                    f"❌ {user.mention} doesn't have {role}.", ephemeral=True
                )
                return
            self.bot.permission_checker.invalidate_user_cache(interaction.guild_id, user.id)
            await interaction.followup.send(
                f"✅ Revoked {role} from {user.mention}", ephemeral=True
            )
        except Exception as e:
            logger.error(f"revoke_role error: {e}", exc_info=True)
            await interaction.followup.send("❌ Error revoking role.", ephemeral=True)

    @app_commands.command(
        name="list_permissions",
        description="List all user permissions",
    )
    @app_commands.default_permissions(administrator=True)
    async def list_permissions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT user_id, role FROM user_permissions WHERE server_id = $1 AND is_active = true ORDER BY CASE role WHEN 'super_admin' THEN 3 WHEN 'admin' THEN 2 WHEN 'moderator' THEN 1 END DESC",
                    interaction.guild_id,
                )
            if not rows:
                await interaction.followup.send("No permissions configured.", ephemeral=True)
                return
            role_emoji = {"super_admin": "👑", "admin": "🛡️", "moderator": "🔰"}
            lines = [
                f"{role_emoji.get(r['role'], '•')} <@{r['user_id']}> - {r['role'].replace('_', ' ').title()}"
                for r in rows[:25]
            ]
            response = "**User Permissions:**\n\n" + "\n".join(lines)
            if len(rows) > 25:
                response += f"\n*... and {len(rows) - 25} more*"
            await interaction.followup.send(response, ephemeral=True)
        except Exception as e:
            logger.error(f"list_permissions error: {e}", exc_info=True)
            await interaction.followup.send("❌ Error fetching permissions.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PermissionCommands(bot))
