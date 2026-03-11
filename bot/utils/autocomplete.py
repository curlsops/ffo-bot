import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands

from config.constants import Constants

if TYPE_CHECKING:
    from bot.client import FFOBot

logger = logging.getLogger(__name__)

MAX_CHOICES = 25


async def cached_autocomplete(
    interaction: discord.Interaction,
    current: str,
    cache_key_template: str,
    fetch_rows: Callable[[object, int], Awaitable[list]],
    to_choices: Callable[[list[dict], str], list[app_commands.Choice[str]]],
    ttl: int = Constants.CACHE_TTL,
    log_prefix: str = "Autocomplete",
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    try:
        bot = cast("FFOBot", interaction.client)  # FFOBot adds cache, db_pool
        guild_id = interaction.guild_id
        cache_key = cache_key_template.format(server_id=guild_id)
        rows = bot.cache.get(cache_key) if bot.cache else None
        if rows is None:
            rows = await fetch_rows(bot.db_pool, guild_id)
            rows = [dict(r) for r in rows]
            if bot.cache:
                bot.cache.set(cache_key, rows, ttl=ttl)
        return to_choices(rows, current)[:MAX_CHOICES]
    except Exception as e:
        logger.debug("%s failed: %s", log_prefix, e)
        return []
