import json
import logging
import traceback

import discord

logger = logging.getLogger(__name__)


CACHE_KEY = "notify_channel:{server_id}"


class AdminNotifier:
    def __init__(self, bot):
        self.bot = bot

    async def get_notify_channel_id(self, server_id: int) -> int | None:
        cache_key = CACHE_KEY.format(server_id=server_id)
        if self.bot.cache:
            cached = self.bot.cache.get(cache_key)
            if cached is not None:
                return None if cached == -1 else cached
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        if not row or not row["config"]:
            result = None
        elif not isinstance(row["config"], dict):
            result = None
        elif channel_id := row["config"].get("notify_channel_id"):
            result = int(channel_id)
        else:
            result = None
        if self.bot.cache:
            self.bot.cache.set(cache_key, result if result is not None else -1, ttl=300)
        return result

    async def get_notify_channel(self, server_id: int) -> discord.TextChannel | None:
        channel_id = await self.get_notify_channel_id(server_id)
        if not channel_id:
            return None
        ch = self.bot.get_channel(channel_id)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(channel_id)
            except Exception:
                logger.warning("Could not fetch notify channel %s", channel_id)
        return ch

    async def set_notify_channel(self, server_id: int, channel_id: int | None) -> bool:
        try:
            async with self.bot.db_pool.acquire() as conn:
                if channel_id:
                    await conn.execute(
                        "UPDATE servers SET config = COALESCE(config, '{}'::jsonb) || $1::jsonb, updated_at = NOW() WHERE server_id = $2",
                        json.dumps({"notify_channel_id": channel_id}),
                        server_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE servers SET config = config - 'notify_channel_id', updated_at = NOW() WHERE server_id = $1",
                        server_id,
                    )
            if self.bot.cache:
                self.bot.cache.delete(CACHE_KEY.format(server_id=server_id))
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

    async def notify_error(
        self,
        server_id: int,
        error: Exception,
        context: str,
        user_id: int | None = None,
        channel_id: int | None = None,
    ):
        embed = discord.Embed(
            title="Error", description=f"**{context}**", color=discord.Color.red()
        )
        embed.add_field(name="Type", value=type(error).__name__, inline=True)
        embed.add_field(name="Message", value=str(error)[:1024] or "No message", inline=False)
        if user_id:
            embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
        if channel_id:
            embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        tb = tb[-1021:] + "..." if len(tb) > 1024 else tb
        embed.add_field(name="Traceback", value=f"```\n{tb}\n```", inline=False)
        await self.send(server_id, embed)
