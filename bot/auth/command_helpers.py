from typing import TYPE_CHECKING

import discord

from bot.auth.permissions import PermissionContext
from config.constants import Role

if TYPE_CHECKING:
    from bot.client import FFOBot


async def require_admin(i: discord.Interaction, cmd: str, bot: "FFOBot") -> bool:
    if not i.guild_id or not bot.permission_checker:
        return False
    ctx = PermissionContext(server_id=i.guild_id, user_id=i.user.id, command_name=cmd)
    if await bot.permission_checker.check_role(ctx, Role.ADMIN):
        return True
    await i.followup.send("Admin required.", ephemeral=True)
    return False


async def require_mod(i: discord.Interaction, cmd: str, bot: "FFOBot") -> bool:
    if not i.guild_id or not bot.permission_checker:
        return False
    ctx = PermissionContext(server_id=i.guild_id, user_id=i.user.id, command_name=cmd)
    if await bot.permission_checker.check_role(ctx, Role.MODERATOR):
        return True
    await i.followup.send("Moderator or higher required.", ephemeral=True)
    return False


async def require_super_admin(i: discord.Interaction, cmd: str, bot: "FFOBot") -> bool:
    if not i.guild_id or not bot.permission_checker:
        return False
    ctx = PermissionContext(server_id=i.guild_id, user_id=i.user.id, command_name=cmd)
    if await bot.permission_checker.check_role(ctx, Role.SUPER_ADMIN):
        return True
    await i.followup.send("❌ Super Admin required.", ephemeral=True)
    return False


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
