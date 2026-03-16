from __future__ import annotations

from datetime import datetime

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


def discord_timestamp(dt: datetime, fmt: str = "R") -> str:
    return f"<t:{int(dt.timestamp())}:{fmt}>"
