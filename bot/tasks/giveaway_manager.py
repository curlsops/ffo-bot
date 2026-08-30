import logging
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from bot.auth.permissions import PermissionContext
from bot.commands.giveaway import CACHE_GIVEAWAY_MESSAGE_ID
from bot.services.giveaway_repository import get_repository
from bot.services.giveaway_service import (
    build_end_announcement,
    finalize_and_announce,
    select_winners,
)
from bot.utils.db import TRANSIENT_DB_ERRORS
from bot.utils.telemetry import trace_span
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
            expired = await get_repository(self.bot).fetch_expired(datetime.now(timezone.utc))
            with trace_span(
                "giveaway.check_tick",
                feature="giveaway",
                attributes={"giveaway.expired_count": len(expired)},
            ):
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
        with trace_span(
            "giveaway.end",
            feature="giveaway",
            attributes={
                "discord.guild_id": str(giveaway["server_id"]),
                "giveaway.id": str(giveaway["id"]),
                "giveaway.winners_count": giveaway["winners_count"],
            },
        ):
            try:
                now = datetime.now(timezone.utc)
                giveaway_repo = get_repository(self.bot)
                await giveaway_repo.mark_ended(
                    giveaway["id"],
                    now,
                    cache=self.bot.cache,
                    message_id=giveaway["message_id"],
                )
                entries = await giveaway_repo.fetch_entries(giveaway["id"])
                if self.bot.cache:
                    self.bot.cache.delete(
                        CACHE_GIVEAWAY_MESSAGE_ID.format(server_id=giveaway["server_id"])
                    )

                winners = select_winners(entries, giveaway["winners_count"])
                if winners:
                    await giveaway_repo.set_winners(giveaway["id"], set(winners))

                g = dict(giveaway)
                g["ended_at"] = now
                channel = await finalize_and_announce(
                    self.bot,
                    g,
                    winners,
                    len(entries),
                    build_end_announcement(giveaway["prize"], winners),
                )
                if not channel:
                    return

                if winners:
                    await self._create_prize_thread(channel, giveaway, winners)

                if self.bot.notifier:
                    try:
                        await self.bot.notifier.notify_giveaway_ended(
                            giveaway["server_id"],
                            giveaway["prize"],
                            winners,
                            len(entries),
                        )
                    except Exception as e:
                        logger.warning("Notify giveaway ended failed: %s", e)
            except Exception as e:
                logger.error("End giveaway error %s: %s", giveaway["id"], e, exc_info=True)
                if self.bot.metrics:
                    self.bot.metrics.errors_total.labels(error_type="giveaway_end").inc()

    async def _create_prize_thread(
        self, channel: discord.TextChannel, giveaway: dict, winners: list
    ):
        with trace_span(
            "giveaway.create_prize_thread",
            feature="giveaway",
            attributes={
                "discord.channel_id": str(channel.id),
                "giveaway.id": str(giveaway["id"]),
                "giveaway.winner_count": len(winners),
            },
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
                if self.bot.metrics:
                    self.bot.metrics.errors_total.labels(error_type="giveaway_prize_thread").inc()
            except Exception as e:
                logger.warning(
                    "Could not create prize thread for giveaway %s: %s",
                    giveaway["id"],
                    e,
                )
                if self.bot.metrics:
                    self.bot.metrics.errors_total.labels(error_type="giveaway_prize_thread").inc()


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayManager(bot))
