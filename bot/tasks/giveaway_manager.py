import logging
import random
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from bot.auth.permissions import PermissionContext
from bot.commands.giveaway import CACHE_GIVEAWAY_MESSAGE_ID
from bot.utils.db import TRANSIENT_DB_ERRORS
from bot.utils.discord_helpers import get_or_fetch_channel
from bot.views.giveaway import GIVEAWAY_COLUMNS
from config.constants import Role

logger = logging.getLogger(__name__)


def _parse_host_from_message(msg: discord.Message) -> int | None:
    if not msg.content:
        return None
    m = re.search(r"<@!?(\d+)>", msg.content)
    return int(m.group(1)) if m else None


class CloseGiveawayThreadView(discord.ui.View):
    def __init__(self, host_id: int, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.host_id = host_id

        btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="🔒",
            custom_id="giveaway:close_thread",
        )
        btn.callback = self._close_callback
        self.add_item(btn)

    async def _close_callback(self, interaction: discord.Interaction):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("Not in a thread.", ephemeral=True)
            return

        bot = interaction.client
        host_id = self.host_id or _parse_host_from_message(interaction.message)
        ctx = PermissionContext(server_id=interaction.guild_id, user_id=interaction.user.id)
        can_close = (
            interaction.user.guild_permissions.administrator
            or (
                getattr(bot, "permission_checker", None)
                and await bot.permission_checker.check_role(ctx, Role.MODERATOR)
            )
            or (host_id and interaction.user.id == host_id)
        )

        if not can_close:
            await interaction.response.send_message(
                "Only the host, server admins, or bot moderators can close this thread.",
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer(ephemeral=False)
        except discord.NotFound:  # interaction expired
            return
        try:
            await thread.edit(locked=True, archived=True)
            closed_embed = discord.Embed(
                title="🔒 Thread Closed",
                description="This thread has been closed and archived.",
                color=discord.Color.dark_grey(),
            )
            await interaction.followup.send(embed=closed_embed)
            self.stop()
        except Exception as e:
            logger.warning("Could not close giveaway thread %s: %s", thread.id, e)
            await interaction.followup.send("Failed to close thread.", ephemeral=True)


class GiveawayManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        if getattr(self.bot.settings, "feature_giveaways", True):
            self.check_giveaways.start()

    async def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(seconds=15)
    async def check_giveaways(self):
        try:
            async with self.bot.db_pool.acquire() as conn:
                expired = await conn.fetch(
                    "SELECT "
                    + GIVEAWAY_COLUMNS
                    + " FROM giveaways WHERE is_active = true AND ends_at <= $1",
                    datetime.now(timezone.utc),
                )
            for g in expired:
                await self._end_giveaway(g)
        except TRANSIENT_DB_ERRORS as e:
            logger.warning("Giveaway check skipped (DB unavailable): %s", e)
        except Exception as e:
            logger.error("Giveaway check error: %s", e, exc_info=True)

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
            if self.bot.cache:
                self.bot.cache.delete(
                    CACHE_GIVEAWAY_MESSAGE_ID.format(server_id=giveaway["server_id"])
                )

            winners = self._select_winners(entries, giveaway["winners_count"])
            if winners:
                async with self.bot.db_pool.acquire() as conn:
                    await conn.executemany(
                        "UPDATE giveaway_entries SET is_winner = true WHERE giveaway_id = $1 AND user_id = $2",
                        [(giveaway["id"], w) for w in winners],
                    )

            channel = await get_or_fetch_channel(self.bot, giveaway["channel_id"])
            if not channel:
                logger.warning(
                    "Could not fetch channel %s for giveaway %s",
                    giveaway["channel_id"],
                    giveaway["id"],
                )
                return

            try:
                msg = await channel.fetch_message(giveaway["message_id"])
                g = dict(giveaway)
                g["ended_at"] = now
                await msg.edit(embed=self._build_ended_embed(g, winners, len(entries)), view=None)
            except discord.NotFound:  # message already deleted
                pass

            if winners:
                mentions = " ".join(f"<@{w}>" for w in winners)
                await channel.send(
                    f"🎉 Congratulations {mentions}! You won **{giveaway['prize']}**!"
                )
                await self._create_prize_thread(channel, giveaway, winners)
            else:
                await channel.send(f"No entries for **{giveaway['prize']}**. No winners.")

            if self.bot.notifier:
                try:
                    await self.bot.notifier.notify_giveaway_ended(
                        giveaway["server_id"], giveaway["prize"], winners, len(entries)
                    )
                except Exception as e:
                    logger.warning("Notify giveaway ended failed: %s", e)
        except Exception as e:
            logger.error("End giveaway error %s: %s", giveaway["id"], e, exc_info=True)

    async def _create_prize_thread(
        self, channel: discord.TextChannel, giveaway: dict, winners: list
    ):
        try:
            thread = await channel.create_thread(
                name=giveaway["prize"][:80],
                message=None,
                invitable=False,
            )
            host_id = giveaway["host_id"]
            for user_id in [host_id] + winners:
                try:
                    await thread.add_user(discord.Object(id=user_id))
                except (discord.Forbidden, discord.HTTPException) as e:
                    logger.warning("Could not add user %s to prize thread: %s", user_id, e)

            host_mention = f"<@{host_id}>"
            winner_mentions = " ".join(f"<@{w}>" for w in winners)
            view = CloseGiveawayThreadView(host_id=host_id, timeout=None)

            embed = discord.Embed(
                title="🎉 Giveaway Ended",
                description=(
                    f"**Prize:** {giveaway['prize']}\n\n"
                    f"**Host:** {host_mention}\n"
                    f"**Winners:** {winner_mentions}\n\n"
                    "Congratulations! Prizes will be handled in this thread."
                ),
                color=discord.Color.gold(),
            )
            await thread.send(
                content=f"{host_mention} {winner_mentions}",
                embed=embed,
                view=view,
            )
        except discord.Forbidden:
            logger.warning(
                "Cannot create prize thread (missing create_private_threads?): %s",
                giveaway["id"],
            )
        except Exception as e:
            logger.warning("Could not create prize thread for giveaway %s: %s", giveaway["id"], e)

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
        ended_at = giveaway["ended_at"]
        ts_full = f"<t:{int(ended_at.timestamp())}:F>"

        lines = [
            f"**{giveaway['prize']}**",
            "",
            f"**Ended:** {ts_full}",
            f"**Hosted by:** <@{giveaway['host_id']}>",
        ]
        if giveaway.get("donor_id"):
            lines.append(f"**Donated by:** <@{giveaway['donor_id']}>")
        description = "\n".join(lines)

        embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED 🎉",
            description=description,
            color=discord.Color.dark_grey(),
            timestamp=ended_at,
        )
        if winners:
            embed.add_field(
                name="Winners", value="\n".join(f"<@{w}>" for w in winners), inline=False
            )
        else:
            embed.add_field(name="Winners", value="No valid entries", inline=False)
        entry_word = "entry" if entry_count == 1 else "entries"
        winner_word = "winner" if len(winners) == 1 else "winners"
        footer = f"{entry_count} {entry_word}"
        if winners:
            footer = f"{len(winners)} {winner_word} • {footer}"
        embed.set_footer(text=footer)
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayManager(bot))
