import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.pagination import truncate_for_discord
from bot.utils.server_roles import get_server_role_ids, set_server_role
from config.constants import Role

logger = logging.getLogger(__name__)

PER_PAGE = 10

ROLE_EMOJI = {"super_admin": "👑", "admin": "🛡️", "moderator": "🔰"}

ROLE_CHOICES = [
    app_commands.Choice(name="Admin", value="admin"),
    app_commands.Choice(name="Moderator", value="moderator"),
]

LEVEL_CHOICES = [
    app_commands.Choice(name="Super Admin", value="super_admin"),
    app_commands.Choice(name="Admin", value="admin"),
    app_commands.Choice(name="Moderator", value="moderator"),
]


MAX_AUTOCOMPLETE_CHOICES = 25


async def _permissions_user_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []
    cur = current.lower().strip()
    choices = []
    for m in interaction.guild.members:
        if m.bot:
            continue
        name = m.display_name or m.name
        if not cur or cur in name.lower() or cur in (m.name or "").lower():
            choices.append(app_commands.Choice(name=name[:100], value=str(m.id)))
    return choices[:MAX_AUTOCOMPLETE_CHOICES]


def _role_members(guild: discord.Guild, role_ids: dict) -> list[tuple[int, Role]]:
    user_highest: dict[int, Role] = {}
    for r in (Role.SUPER_ADMIN, Role.ADMIN, Role.MODERATOR):
        if r not in role_ids:
            continue
        role = guild.get_role(role_ids[r])
        if role:
            for m in role.members:
                if m.id not in user_highest or r.hierarchy > user_highest[m.id].hierarchy:
                    user_highest[m.id] = r
    return sorted(user_highest.items(), key=lambda x: (-x[1].hierarchy, x[0]))


def _make_perm_nav_buttons(view: "PermissionsListView") -> tuple[discord.ui.Button, ...]:
    toggle = discord.ui.Button(
        label="User Mapped" if view.mode == "role" else "Role Mapped",
        style=discord.ButtonStyle.primary,
        custom_id="perm:toggle",
        row=0,
    )
    toggle.callback = view._toggle_callback
    prev_btn = discord.ui.Button(
        label="◀",
        style=discord.ButtonStyle.secondary,
        custom_id="perm:prev",
        row=0,
    )
    prev_btn.callback = view._prev_callback
    page_btn = discord.ui.Button(
        label="1/1",
        style=discord.ButtonStyle.success,
        custom_id="perm:page",
        disabled=True,
        row=0,
    )
    next_btn = discord.ui.Button(
        label="▶",
        style=discord.ButtonStyle.secondary,
        custom_id="perm:next",
        row=0,
    )
    next_btn.callback = view._next_callback
    return toggle, prev_btn, page_btn, next_btn


class PermissionsListView(discord.ui.View):
    def __init__(
        self,
        role_ids: dict,
        role_members: list[tuple[int, Role]],
        user_rows: list,
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.role_ids = role_ids
        self.role_members = role_members
        self.user_rows = user_rows
        self.mode = "role" if role_ids or role_members else "user"
        self.page = 0
        self._max_page = 0
        self._update_max_page()
        self.page_btn = None
        for btn in _make_perm_nav_buttons(self):
            if btn.custom_id == "perm:page":
                self.page_btn = btn
            self.add_item(btn)
        self._update_buttons()

    def _update_max_page(self):
        items = self.role_members if self.mode == "role" else self.user_rows
        self._max_page = max(0, (len(items) - 1) // PER_PAGE)

    def _format_page(self) -> str:
        if self.mode == "role":
            header = "**Discord role config:**\n"
            if self.role_ids:
                header += "\n".join(
                    f"{ROLE_EMOJI.get(r.value, '•')} **{r.value.replace('_', ' ').title()}:** <@&{self.role_ids[r]}>"
                    for r in (Role.SUPER_ADMIN, Role.ADMIN, Role.MODERATOR)
                    if r in self.role_ids
                )
                header += "\n\n**Members with these roles:**\n"
            else:
                header += "*(no roles configured)*\n\n"
            items = self.role_members
            start = self.page * PER_PAGE
            chunk = items[start : start + PER_PAGE]
            lines = [
                f"{ROLE_EMOJI.get(role.value, '•')} <@{uid}> - {role.value.replace('_', ' ').title()}"
                for uid, role in chunk
            ]
        else:
            header = "**User permissions (per-user grants):**\n\n"
            items = self.user_rows
            start = self.page * PER_PAGE
            chunk = items[start : start + PER_PAGE]
            lines = [
                f"{ROLE_EMOJI.get(r['role'], '•')} <@{r['user_id']}> - {r['role'].replace('_', ' ').title()}"
                for r in chunk
            ]
        body = "\n".join(lines) if lines else "*(none)*"
        return truncate_for_discord(header + body)

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self._max_page + 1}"
        for child in self.children:
            if child.custom_id == "perm:prev":
                child.disabled = self.page <= 0
            elif child.custom_id == "perm:next":
                child.disabled = self.page >= self._max_page
            elif child.custom_id == "perm:toggle":
                child.label = "User Mapped" if self.mode == "role" else "Role Mapped"

    async def _toggle_callback(self, interaction: discord.Interaction):
        self.mode = "user" if self.mode == "role" else "role"
        self.page = 0
        self._update_max_page()
        self._update_buttons()
        await interaction.response.edit_message(content=self._format_page(), view=self)

    async def _prev_callback(self, interaction: discord.Interaction):
        if self.page <= 0:
            return
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(content=self._format_page(), view=self)

    async def _next_callback(self, interaction: discord.Interaction):
        if self.page >= self._max_page:
            return
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(content=self._format_page(), view=self)


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
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Server only.", ephemeral=True)
            return

        try:
            role_ids = await get_server_role_ids(bot.db_pool, interaction.guild_id, cache=bot.cache)
            role_members = _role_members(guild, role_ids) if role_ids else []
            async with bot.db_pool.acquire() as conn:
                user_rows = await conn.fetch(
                    "SELECT user_id, role FROM user_permissions WHERE server_id = $1 AND is_active = true ORDER BY CASE role WHEN 'super_admin' THEN 3 WHEN 'admin' THEN 2 WHEN 'moderator' THEN 1 END DESC",
                    interaction.guild_id,
                )
        except Exception as e:
            logger.error("permissions list error: %s", e, exc_info=True)
            await interaction.followup.send("❌ Error fetching permissions.", ephemeral=True)
            return

        if not role_ids and not role_members and not user_rows:
            await interaction.followup.send(
                "No permissions configured. Use `/permissions add` for per-user grants, or `/permissions set` for Discord role mappings.",
                ephemeral=True,
            )
            return

        view = PermissionsListView(
            role_ids=role_ids or {},
            role_members=role_members,
            user_rows=list(user_rows),
        )
        await interaction.followup.send(
            view._format_page(),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="add", description="Grant Admin or Moderator to a user")
    @app_commands.describe(user="User to grant role to", role="Role to grant")
    @app_commands.choices(role=ROLE_CHOICES)
    @app_commands.autocomplete(user=_permissions_user_autocomplete)
    async def add_cmd(self, interaction: discord.Interaction, user: str, role: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_super_admin(interaction, "permissions add"):
            return
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Server only.", ephemeral=True)
            return
        try:
            user_id = int(user)
        except ValueError:
            await interaction.followup.send("❌ Invalid user.", ephemeral=True)
            return
        target = guild.get_member(user_id) or await self.cog.bot.fetch_user(user_id)
        if not target:
            await interaction.followup.send("❌ User not found.", ephemeral=True)
            return
        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                existing = await conn.fetchval(
                    "SELECT 1 FROM user_permissions WHERE server_id = $1 AND user_id = $2 AND role = $3 AND is_active = true LIMIT 1",
                    interaction.guild_id,
                    user_id,
                    role,
                )
                if existing:
                    await interaction.followup.send(
                        f"{target.mention} already has {role}.", ephemeral=True
                    )
                    return
                await conn.execute(
                    "INSERT INTO user_permissions (server_id, user_id, role, granted_by) VALUES ($1, $2, $3, $4)",
                    interaction.guild_id,
                    user_id,
                    role,
                    interaction.user.id,
                )
            self.cog.bot.permission_checker.invalidate_user_cache(interaction.guild_id, user_id)
            if self.cog.bot.notifier:
                await self.cog.bot.notifier.notify_permission_changed(
                    interaction.guild_id,
                    "Granted",
                    role,
                    user_id,
                    interaction.user.id,
                )
            await interaction.followup.send(
                f"✅ Granted {role} to {target.mention}", ephemeral=True
            )
        except Exception as e:
            logger.error("permissions add error: %s", e, exc_info=True)
            await interaction.followup.send("❌ Error granting role.", ephemeral=True)

    @app_commands.command(name="remove", description="Revoke Admin or Moderator from a user")
    @app_commands.describe(user="User to revoke role from", role="Role to revoke")
    @app_commands.choices(role=ROLE_CHOICES)
    @app_commands.autocomplete(user=_permissions_user_autocomplete)
    async def remove_cmd(self, interaction: discord.Interaction, user: str, role: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_super_admin(interaction, "permissions remove"):
            return
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Server only.", ephemeral=True)
            return
        try:
            user_id = int(user)
        except ValueError:
            await interaction.followup.send("❌ Invalid user.", ephemeral=True)
            return
        target = guild.get_member(user_id) or await self.cog.bot.fetch_user(user_id)
        if not target:
            await interaction.followup.send("❌ User not found.", ephemeral=True)
            return
        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE user_permissions SET is_active = false, revoked_at = NOW() WHERE server_id = $1 AND user_id = $2 AND role = $3 AND is_active = true",
                    interaction.guild_id,
                    user_id,
                    role,
                )
            if result == "UPDATE 0":
                await interaction.followup.send(
                    f"❌ {target.mention} doesn't have {role}.", ephemeral=True
                )
                return
            self.cog.bot.permission_checker.invalidate_user_cache(interaction.guild_id, user_id)
            if self.cog.bot.notifier:
                await self.cog.bot.notifier.notify_permission_changed(
                    interaction.guild_id,
                    "Revoked",
                    role,
                    user_id,
                    interaction.user.id,
                )
            await interaction.followup.send(
                f"✅ Revoked {role} from {target.mention}", ephemeral=True
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
            server_name=interaction.guild.name if interaction.guild else None,
        )
        if not success:
            await interaction.followup.send("❌ Failed to update.", ephemeral=True)
            return
        if self.cog.bot.notifier:
            await self.cog.bot.notifier.notify_permission_changed(
                interaction.guild_id,
                "Set role",
                level,
                discord_role.id if discord_role else None,
                interaction.user.id,
                discord_role=discord_role.id if discord_role else None,
            )
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
