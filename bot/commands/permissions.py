"""Permission management commands - nested under /permissions."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.server_roles import get_server_role_ids, set_server_role
from config.constants import Role

logger = logging.getLogger(__name__)

ROLE_CHOICES = [
    app_commands.Choice(name="Admin", value="admin"),
    app_commands.Choice(name="Moderator", value="moderator"),
]

LEVEL_CHOICES = [
    app_commands.Choice(name="Super Admin", value="super_admin"),
    app_commands.Choice(name="Admin", value="admin"),
    app_commands.Choice(name="Moderator", value="moderator"),
]


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class PermissionsGroup(app_commands.Group):
    """Manage permissions - user grants and Discord role mappings."""

    def __init__(self, cog: "PermissionCommands"):
        super().__init__(name="permissions", description="Manage permissions")
        self.cog = cog

    async def _check_super_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.cog.bot.permission_checker.check_role(ctx, Role.SUPER_ADMIN):
            await interaction.followup.send("❌ Super Admin required.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="list", description="List user permissions and role config")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_super_admin(interaction, "permissions list"):
            return

        bot = self.cog.bot
        parts = []

        # Role config (Discord role mappings)
        role_ids = await get_server_role_ids(bot.db_pool, interaction.guild_id, cache=bot.cache)
        if role_ids:
            lines = [
                f"**{r.value.replace('_', ' ').title()}:** <@&{role_ids[r]}>"
                for r in (Role.SUPER_ADMIN, Role.ADMIN, Role.MODERATOR)
                if r in role_ids
            ]
            parts.append("**Discord role config:**\n" + "\n".join(lines))

        # User permissions
        try:
            async with bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT user_id, role FROM user_permissions WHERE server_id = $1 AND is_active = true ORDER BY CASE role WHEN 'super_admin' THEN 3 WHEN 'admin' THEN 2 WHEN 'moderator' THEN 1 END DESC",
                    interaction.guild_id,
                )
            if rows:
                role_emoji = {"super_admin": "👑", "admin": "🛡️", "moderator": "🔰"}
                lines = [
                    f"{role_emoji.get(r['role'], '•')} <@{r['user_id']}> - {r['role'].replace('_', ' ').title()}"
                    for r in rows[:25]
                ]
                section = "**User permissions:**\n" + "\n".join(lines)
                if len(rows) > 25:
                    section += f"\n*... and {len(rows) - 25} more*"
                parts.append(section)
        except Exception as e:
            logger.error("permissions list error: %s", e, exc_info=True)
            await interaction.followup.send("❌ Error fetching permissions.", ephemeral=True)
            return

        if not parts:
            await interaction.followup.send(
                "No permissions configured. Use `/permissions add` for per-user grants, or `/permissions set` for Discord role mappings.",
                ephemeral=True,
            )
            return
        await interaction.followup.send("\n\n".join(parts), ephemeral=True)


    @app_commands.command(name="add", description="Grant Admin or Moderator to a user")
    @app_commands.describe(user="User to grant role to", role="Role to grant")
    @app_commands.choices(role=ROLE_CHOICES)
    async def add_cmd(self, interaction: discord.Interaction, user: discord.User, role: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_super_admin(interaction, "permissions add"):
            return
        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO user_permissions (server_id, user_id, role, granted_by) VALUES ($1, $2, $3, $4) ON CONFLICT (server_id, user_id, role, is_active) WHERE is_active = true DO NOTHING",
                    interaction.guild_id,
                    user.id,
                    role,
                    interaction.user.id,
                )
            self.cog.bot.permission_checker.invalidate_user_cache(
                interaction.guild_id, user.id
            )
            await interaction.followup.send(f"✅ Granted {role} to {user.mention}", ephemeral=True)
        except Exception as e:
            logger.error("permissions add error: %s", e, exc_info=True)
            await interaction.followup.send("❌ Error granting role.", ephemeral=True)

    @app_commands.command(name="remove", description="Revoke Admin or Moderator from a user")
    @app_commands.describe(user="User to revoke role from", role="Role to revoke")
    @app_commands.choices(role=ROLE_CHOICES)
    async def remove_cmd(self, interaction: discord.Interaction, user: discord.User, role: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_super_admin(interaction, "permissions remove"):
            return
        try:
            async with self.cog.bot.db_pool.acquire() as conn:
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
            self.cog.bot.permission_checker.invalidate_user_cache(
                interaction.guild_id, user.id
            )
            await interaction.followup.send(
                f"✅ Revoked {role} from {user.mention}", ephemeral=True
            )
        except Exception as e:
            logger.error("permissions remove error: %s", e, exc_info=True)
            await interaction.followup.send("❌ Error revoking role.", ephemeral=True)

    @app_commands.command(
        name="set",
        description="Set a Discord role for Admin/Mod/Super Admin (leave empty to clear)",
    )
    @app_commands.describe(
        level="Permission level",
        discord_role="Discord role (leave empty to clear)",
    )
    @app_commands.choices(level=LEVEL_CHOICES)
    async def set_cmd(
        self,
        interaction: discord.Interaction,
        level: str,
        discord_role: discord.Role | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_super_admin(interaction, "permissions set"):
            return
        await self.cog.bot._register_server(interaction.guild)
        role_enum = Role(level)
        success = await set_server_role(
            self.cog.bot.db_pool,
            interaction.guild_id,
            role_enum,
            discord_role.id if discord_role else None,
            cache=self.cog.bot.cache,
        )
        if not success:
            await interaction.followup.send("❌ Failed to update.", ephemeral=True)
            return
        label = level.replace("_", " ").title()
        if discord_role:
            await interaction.followup.send(
                f"✅ {label} role set to {discord_role.mention}.", ephemeral=True
            )
        else:
            await interaction.followup.send(f"✅ {label} role cleared.", ephemeral=True)


class PermissionCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.permissions_group = PermissionsGroup(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.permissions_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.permissions_group.name)


async def setup(bot):
    await bot.add_cog(PermissionCommands(bot))
