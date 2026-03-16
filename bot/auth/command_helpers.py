from typing import TYPE_CHECKING

import discord

from bot.auth.permissions import PermissionContext
from config.constants import Role

if TYPE_CHECKING:
    from bot.client import FFOBot


def _require_role_msg(role: Role) -> str:
    return {
        Role.SUPER_ADMIN: "❌ Super Admin required.",
        Role.ADMIN: "Admin required.",
        Role.MODERATOR: "Moderator or higher required.",
    }[role]


async def require_role(i: discord.Interaction, cmd: str, bot: "FFOBot", role: Role) -> bool:
    if not i.guild_id or not bot.permission_checker:
        return False
    ctx = PermissionContext(server_id=i.guild_id, user_id=i.user.id, command_name=cmd)
    if await bot.permission_checker.check_role(ctx, role):
        return True
    await i.followup.send(_require_role_msg(role), ephemeral=True)
    return False


async def require_admin(i: discord.Interaction, cmd: str, bot: "FFOBot") -> bool:
    return await require_role(i, cmd, bot, Role.ADMIN)


async def require_mod(i: discord.Interaction, cmd: str, bot: "FFOBot") -> bool:
    return await require_role(i, cmd, bot, Role.MODERATOR)


async def require_super_admin(i: discord.Interaction, cmd: str, bot: "FFOBot") -> bool:
    return await require_role(i, cmd, bot, Role.SUPER_ADMIN)


async def require_rcon(i: discord.Interaction, bot: "FFOBot") -> bool:
    if bot.minecraft_rcon:
        return True
    await i.followup.send("Minecraft whitelist is not configured for this server.", ephemeral=True)
    return False


async def require_guild(i: discord.Interaction) -> bool:
    if i.guild_id:
        return True
    await i.followup.send("❌ Server only.", ephemeral=True)
    return False


async def send_error(i: discord.Interaction, msg: str) -> None:
    await i.followup.send(f"❌ {msg}" if not msg.startswith("❌") else msg, ephemeral=True)
