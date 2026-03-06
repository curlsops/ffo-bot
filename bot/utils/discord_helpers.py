from __future__ import annotations

import discord


async def get_or_fetch_channel(
    bot: discord.Client, channel_id: int
) -> discord.abc.GuildChannel | None:
    ch = bot.get_channel(channel_id)
    if ch is not None:
        return ch
    try:
        return await bot.fetch_channel(channel_id)
    except Exception:
        return None
