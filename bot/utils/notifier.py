import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)


class AdminNotifier:
    def __init__(self, bot):
        self.bot = bot

    async def get_notify_channel(self, server_id: int) -> Optional[discord.TextChannel]:
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        if not row or not row["config"]:
            return None
        channel_id = row["config"].get("notify_channel_id")
        return self.bot.get_channel(int(channel_id)) if channel_id else None

    async def set_notify_channel(self, server_id: int, channel_id: Optional[int]) -> bool:
        try:
            async with self.bot.db_pool.acquire() as conn:
                if channel_id:
                    await conn.execute(
                        "UPDATE servers SET config = config || $1::jsonb, updated_at = NOW() WHERE server_id = $2",
                        {"notify_channel_id": channel_id},
                        server_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE servers SET config = config - 'notify_channel_id', updated_at = NOW() WHERE server_id = $1",
                        server_id,
                    )
            return True
        except Exception:
            logger.exception("Failed to set notify channel")
            return False

    async def send(self, server_id: int, embed: discord.Embed) -> bool:
        channel = await self.get_notify_channel(server_id)
        if not channel:
            return False
        try:
            await channel.send(embed=embed)
            return True
        except Exception:
            logger.exception("Failed to send notification")
            return False

    async def notify_giveaway_created(
        self, server_id: int, prize: str, host_id: int, channel_id: int, ends_at
    ):
        embed = discord.Embed(
            title="Giveaway Created", description=f"**{prize}**", color=discord.Color.green()
        )
        embed.add_field(name="Host", value=f"<@{host_id}>", inline=True)
        embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
        embed.add_field(name="Ends", value=f"<t:{int(ends_at.timestamp())}:R>", inline=True)
        await self.send(server_id, embed)

    async def notify_giveaway_ended(
        self, server_id: int, prize: str, winners: list, entry_count: int
    ):
        embed = discord.Embed(
            title="Giveaway Ended", description=f"**{prize}**", color=discord.Color.blue()
        )
        embed.add_field(name="Entries", value=str(entry_count), inline=True)
        winners_val = ", ".join(f"<@{w}>" for w in winners) if winners else "No valid entries"
        embed.add_field(name="Winners", value=winners_val, inline=False)
        await self.send(server_id, embed)
