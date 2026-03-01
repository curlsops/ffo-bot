import logging
import random
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class GiveawayManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        if getattr(self.bot.settings, "feature_giveaways", True):
            self.check_giveaways.start()

    async def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        try:
            async with self.bot.db_pool.acquire() as conn:
                expired = await conn.fetch(
                    "SELECT * FROM giveaways WHERE is_active = true AND ends_at <= $1",
                    datetime.now(timezone.utc),
                )
            for g in expired:
                await self._end_giveaway(g)
        except Exception as e:
            logger.error(f"Giveaway check error: {e}", exc_info=True)

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def _end_giveaway(self, giveaway):
        try:
            now = datetime.now(timezone.utc)
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE giveaways SET is_active = false, ended_at = $1 WHERE id = $2",
                    now,
                    giveaway["id"],
                )
                entries = await conn.fetch(
                    "SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id = $1",
                    giveaway["id"],
                )

            winners = self._select_winners(entries, giveaway["winners_count"])
            if winners:
                async with self.bot.db_pool.acquire() as conn:
                    await conn.executemany(
                        "UPDATE giveaway_entries SET is_winner = true WHERE giveaway_id = $1 AND user_id = $2",
                        [(giveaway["id"], w) for w in winners],
                    )

            channel = self.bot.get_channel(giveaway["channel_id"])
            if not channel:
                return

            try:
                msg = await channel.fetch_message(giveaway["message_id"])
                g = dict(giveaway)
                g["ended_at"] = now
                await msg.edit(
                    embed=self._build_ended_embed(g, winners, len(entries)), view=None
                )
            except discord.NotFound:
                pass

            if winners:
                mentions = " ".join(f"<@{w}>" for w in winners)
                await channel.send(
                    f"🎉 Congratulations {mentions}! You won **{giveaway['prize']}**!"
                )
            else:
                await channel.send(f"No entries for **{giveaway['prize']}**. No winners.")

            if getattr(self.bot, "notifier", None):
                await self.bot.notifier.notify_giveaway_ended(
                    giveaway["server_id"], giveaway["prize"], winners, len(entries)
                )
        except Exception as e:
            logger.error(f"End giveaway error {giveaway['id']}: {e}", exc_info=True)

    def _select_winners(self, entries: list, count: int) -> list:
        if not entries:
            return []
        weighted = []
        for e in entries:
            weighted.extend([e["user_id"]] * e["entries"])
        random.shuffle(weighted)
        winners, seen = [], set()
        for uid in weighted:
            if uid not in seen:
                winners.append(uid)
                seen.add(uid)
            if len(winners) >= count:
                break
        return winners

    def _build_ended_embed(self, giveaway, winners: list, entry_count: int) -> discord.Embed:
        embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED 🎉",
            description=f"**{giveaway['prize']}**",
            color=discord.Color.dark_grey(),
            timestamp=giveaway["ended_at"],
        )
        donor = f"<@{giveaway['donor_id']}>" if giveaway.get("donor_id") else "N/A"
        embed.add_field(name="Hosted by", value=f"<@{giveaway['host_id']}>", inline=True)
        embed.add_field(name="Donated by", value=donor, inline=True)
        embed.add_field(name="Total Entries", value=str(entry_count), inline=True)
        if winners:
            embed.add_field(
                name="Winners", value="\n".join(f"<@{w}>" for w in winners), inline=False
            )
        else:
            embed.add_field(name="Winners", value="No valid entries", inline=False)
        embed.set_footer(text="Ended at")
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayManager(bot))
