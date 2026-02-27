"""Permission management commands."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role

logger = logging.getLogger(__name__)


class PermissionCommands(commands.Cog):
    """Permission management commands."""

    def __init__(self, bot):
        """
        Initialize permission commands.

        Args:
            bot: Bot instance
        """
        self.bot = bot

    @app_commands.command(
        name="grant_role", description="Grant a role to a user (Super Admin only)"
    )
    @app_commands.describe(user="User to grant role to", role="Role to grant")
    @app_commands.choices(
        role=[
            app_commands.Choice(name="Admin", value="admin"),
            app_commands.Choice(name="Moderator", value="moderator"),
        ]
    )
    async def grant_role(self, interaction: discord.Interaction, user: discord.User, role: str):
        """
        Grant role to user.

        Args:
            interaction: Discord interaction
            user: Target user
            role: Role to grant
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Check permissions (Super Admin only)
            ctx = PermissionContext(
                server_id=interaction.guild_id,
                user_id=interaction.user.id,
                command_name="grant_role",
            )

            has_permission = await self.bot.permission_checker.check_role(ctx, Role.SUPER_ADMIN)
            if not has_permission:
                await interaction.followup.send(
                    "❌ You need Super Admin role to use this command.", ephemeral=True
                )
                return

            # Grant role
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_permissions (server_id, user_id, role, granted_by)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (server_id, user_id, role, is_active)
                    WHERE is_active = true DO NOTHING
                    """,
                    interaction.guild_id,
                    user.id,
                    role,
                    interaction.user.id,
                )

            # Invalidate permission cache
            self.bot.permission_checker.invalidate_user_cache(interaction.guild_id, user.id)

            # Audit log
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log
                    (server_id, user_id, action, target_type, target_id, details)
                    VALUES ($1, $2, 'permission_granted', 'user', $3, $4)
                    """,
                    interaction.guild_id,
                    interaction.user.id,
                    str(user.id),
                    {"role": role, "target_user": user.name},
                )

            await interaction.followup.send(
                f"✅ Granted {role} role to {user.mention}", ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in grant_role command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while granting role.", ephemeral=True
            )

    @app_commands.command(
        name="revoke_role", description="Revoke a role from a user (Super Admin only)"
    )
    @app_commands.describe(user="User to revoke role from", role="Role to revoke")
    @app_commands.choices(
        role=[
            app_commands.Choice(name="Admin", value="admin"),
            app_commands.Choice(name="Moderator", value="moderator"),
        ]
    )
    async def revoke_role(self, interaction: discord.Interaction, user: discord.User, role: str):
        """
        Revoke role from user.

        Args:
            interaction: Discord interaction
            user: Target user
            role: Role to revoke
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Check permissions
            ctx = PermissionContext(
                server_id=interaction.guild_id,
                user_id=interaction.user.id,
                command_name="revoke_role",
            )

            has_permission = await self.bot.permission_checker.check_role(ctx, Role.SUPER_ADMIN)
            if not has_permission:
                await interaction.followup.send(
                    "❌ You need Super Admin role to use this command.", ephemeral=True
                )
                return

            # Revoke role
            async with self.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE user_permissions
                    SET is_active = false, revoked_at = NOW()
                    WHERE server_id = $1 AND user_id = $2 AND role = $3 AND is_active = true
                    """,
                    interaction.guild_id,
                    user.id,
                    role,
                )

            if result == "UPDATE 0":
                await interaction.followup.send(
                    f"❌ User {user.mention} does not have {role} role.", ephemeral=True
                )
                return

            # Invalidate permission cache
            self.bot.permission_checker.invalidate_user_cache(interaction.guild_id, user.id)

            # Audit log
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log
                    (server_id, user_id, action, target_type, target_id, details)
                    VALUES ($1, $2, 'permission_revoked', 'user', $3, $4)
                    """,
                    interaction.guild_id,
                    interaction.user.id,
                    str(user.id),
                    {"role": role, "target_user": user.name},
                )

            await interaction.followup.send(
                f"✅ Revoked {role} role from {user.mention}", ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in revoke_role command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while revoking role.", ephemeral=True
            )

    @app_commands.command(name="list_permissions", description="List all user permissions")
    async def list_permissions(self, interaction: discord.Interaction):
        """
        List all permissions for the server.

        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(ephemeral=True)

        try:
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_id, role, granted_at
                    FROM user_permissions
                    WHERE server_id = $1 AND is_active = true
                    ORDER BY
                        CASE role
                            WHEN 'super_admin' THEN 3
                            WHEN 'admin' THEN 2
                            WHEN 'moderator' THEN 1
                        END DESC,
                        granted_at DESC
                    """,
                    interaction.guild_id,
                )

            if not rows:
                await interaction.followup.send(
                    "No permissions configured for this server.", ephemeral=True
                )
                return

            # Build response
            response = "**User Permissions:**\n\n"
            for row in rows[:25]:
                user = await self.bot.fetch_user(row["user_id"])
                role_emoji = {"super_admin": "👑", "admin": "🛡️", "moderator": "🔰"}
                response += f"{role_emoji.get(row['role'], '•')} {user.mention} - {row['role'].replace('_', ' ').title()}\n"

            if len(rows) > 25:
                response += f"\n*... and {len(rows) - 25} more*"

            await interaction.followup.send(response, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in list_permissions command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching permissions.", ephemeral=True
            )


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(PermissionCommands(bot))
