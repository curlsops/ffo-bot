import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Any

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


def _get_interaction(args: tuple[Any, ...], kwargs: dict[str, Any]) -> discord.Interaction:
    interaction = kwargs.get("interaction")
    if interaction and hasattr(interaction, "response") and hasattr(interaction, "followup"):
        return interaction
    for arg in args:
        if hasattr(arg, "response") and hasattr(arg, "followup"):
            return arg
    raise ValueError("Command interaction argument not found.")


def execute_command(
    *,
    defer_ephemeral: bool = True,
    permission_check: Callable[..., Awaitable[bool]] | None = None,
    error_message: str = "An error occurred.",
    use_send_error: bool = True,
    logger: logging.Logger | None = None,
    log_prefix: str | None = None,
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            interaction = _get_interaction(args, kwargs)
            await interaction.response.defer(ephemeral=defer_ephemeral)

            if permission_check and not await permission_check(*args, **kwargs):
                return

            try:
                await func(*args, **kwargs)
            except Exception as e:
                if logger:
                    prefix = log_prefix or f"{func.__name__} error"
                    logger.error("%s: %s", prefix, e, exc_info=True)
                if use_send_error:
                    await send_error(interaction, error_message)
                else:
                    await interaction.followup.send(error_message, ephemeral=True)

        return wrapper

    return decorator
