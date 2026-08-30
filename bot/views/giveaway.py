import asyncio
import logging
import uuid
from weakref import WeakKeyDictionary

import discord

from bot.services.giveaway_repository import get_repository
from bot.services.giveaway_service import build_embed
from bot.utils.pagination import ListPaginatedView
from bot.utils.telemetry import trace_span

logger = logging.getLogger(__name__)
EMBED_REFRESH_DEBOUNCE_SECONDS = 0.35


class GiveawayEmbedScheduler:
    """Debounces giveaway embed refreshes.

    Coalesces rapid join/leave activity for a giveaway into a single
    Discord message edit, instead of hammering the edit-message API once
    per entry change.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._jobs: dict[uuid.UUID, dict] = {}

    async def schedule_refresh(
        self,
        bot,
        giveaway_id: uuid.UUID,
        *,
        message: discord.Message | None = None,
        channel=None,
        message_id: int | None = None,
    ):
        resolved_message_id = message_id if message_id is not None else getattr(message, "id", None)
        resolved_channel = channel if channel is not None else getattr(message, "channel", None)
        async with self._lock:
            job = self._jobs.get(giveaway_id)
            if not job:
                job = {
                    "dirty": True,
                    "message": message,
                    "channel": resolved_channel,
                    "message_id": resolved_message_id,
                }
                job["task"] = asyncio.create_task(self._run_refresh_job(bot, giveaway_id))
                self._jobs[giveaway_id] = job
                return
            job["dirty"] = True
            if message is not None:
                job["message"] = message
            if resolved_channel is not None:
                job["channel"] = resolved_channel
            if resolved_message_id is not None:
                job["message_id"] = resolved_message_id

    async def _run_refresh_job(self, bot, giveaway_id: uuid.UUID):
        try:
            while True:
                with trace_span(
                    "giveaway.embed_scheduler.debounce",
                    feature="giveaway",
                    attributes={"giveaway.id": str(giveaway_id)},
                ):
                    await asyncio.sleep(EMBED_REFRESH_DEBOUNCE_SECONDS)
                    async with self._lock:
                        job = self._jobs.get(giveaway_id)
                        if not job:
                            return
                        job["dirty"] = False
                        message = job.get("message")
                        channel = job.get("channel")
                        message_id = job.get("message_id")
                    await self._refresh_embed_now_with_fallback(
                        bot,
                        giveaway_id,
                        message=message,
                        channel=channel,
                        message_id=message_id,
                    )
                    async with self._lock:
                        job = self._jobs.get(giveaway_id)
                        if not job:
                            return
                        if job.get("dirty"):
                            continue
                        self._jobs.pop(giveaway_id, None)
                        return
        finally:
            async with self._lock:
                self._jobs.pop(giveaway_id, None)

    async def _refresh_embed_now_with_fallback(
        self,
        bot,
        giveaway_id: uuid.UUID,
        *,
        message: discord.Message | None,
        channel,
        message_id: int | None,
    ):
        target_message = message
        if target_message is None:
            if channel is None or message_id is None:
                return
            try:
                target_message = await channel.fetch_message(message_id)
            except Exception as e:
                logger.debug("Could not fetch giveaway message for refresh: %s", e)
                return
        temp_view = GiveawayView(giveaway_id, bot)
        await temp_view._refresh_embed_now(target_message, giveaway_id)

    async def wait_for_scheduled(self):
        async with self._lock:
            tasks = [job.get("task") for job in self._jobs.values() if job.get("task")]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


_scheduler_registry: "WeakKeyDictionary[object, GiveawayEmbedScheduler]" = WeakKeyDictionary()


def _get_scheduler(bot) -> GiveawayEmbedScheduler:
    scheduler = _scheduler_registry.get(bot)
    if scheduler is None:
        scheduler = GiveawayEmbedScheduler()
        _scheduler_registry[bot] = scheduler
    return scheduler


def _win_probability(user_entries: int, total_entries: int, winners_count: int) -> float:
    if total_entries <= 0 or user_entries <= 0:
        return 0.0
    if user_entries >= total_entries:
        return 1.0
    k = min(winners_count, total_entries)
    if k > total_entries - user_entries:
        return 1.0
    p_not_win = 1.0
    for i in range(k):
        p_not_win *= (total_entries - user_entries - i) / (total_entries - i)
    return 1.0 - p_not_win


def EntriesPaginatedView(
    rows: list,
    winners_count: int = 1,
    user_id: int | None = None,
    timeout: float = 60,
) -> ListPaginatedView:
    total_entries = sum(r["entries"] for r in rows)
    user_entry = next((r for r in rows if r["user_id"] == user_id), None)
    extra: list[discord.ui.Item] = []
    if user_entry:

        async def _my_entry_cb(i: discord.Interaction):
            entries = user_entry["entries"]
            total = total_entries
            pct = _win_probability(entries, total, winners_count) * 100 if total > 0 else 0
            pct_str = f"{pct:.2f}".rstrip("0").rstrip(".") if pct < 100 else "100"
            lines = [
                f"✓ You had **{entries}** {'entry' if entries == 1 else 'entries'} for this giveaway!",
                f"ℹ️ There are a total of **{total}** entries in this giveaway.",
                f"🎁 Your chances of winning: **{pct_str}%**",
            ]
            await i.response.send_message("\n".join(lines), ephemeral=True)

        my_btn = discord.ui.Button(
            label="✓ My Entry",
            style=discord.ButtonStyle.primary,
            custom_id="entries:mine",
            row=0,
        )
        my_btn.callback = _my_entry_cb
        extra = [my_btn]
    view = ListPaginatedView(
        rows,
        "**Giveaway Participants**\n\n",
        lambda r: f"<@{r['user_id']}>",
        extra_items=extra,
        custom_id_prefix="entries",
        timeout=timeout,
    )
    view.max_page = view._max_page
    view.total_entries = total_entries
    return view


class AlreadyJoinedView(discord.ui.View):
    def __init__(self, giveaway_id: uuid.UUID, message_id: int, bot):
        super().__init__(timeout=60)
        self.giveaway_id = giveaway_id
        self.message_id = message_id
        self.bot = bot

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, row=0)
    async def leave_button(
        self, interaction: discord.Interaction, button: discord.ui.Button | None = None
    ):
        with trace_span(
            "giveaway.leave_button",
            feature="giveaway",
            attributes={
                "discord.guild_id": str(interaction.guild_id),
                "giveaway.id": str(self.giveaway_id),
            },
        ):
            await interaction.response.defer(ephemeral=True)
            try:
                removed = await self._remove_entry(interaction)
                if removed:
                    await self._update_giveaway_embed(interaction)
                    await interaction.followup.send(
                        "Your entry for this giveaway has been removed.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send("You are not in this giveaway.", ephemeral=True)
            except Exception as e:
                logger.error("Leave giveaway error: %s", e, exc_info=True)
                if self.bot.metrics:
                    self.bot.metrics.errors_total.labels(error_type="giveaway_leave").inc()
                await interaction.followup.send("Error leaving giveaway.", ephemeral=True)

    async def _remove_entry(self, interaction: discord.Interaction) -> bool:
        return await get_repository(self.bot).remove_entry(
            self.giveaway_id, interaction.user.id, cache=self.bot.cache
        )

    async def _update_giveaway_embed(self, interaction: discord.Interaction):
        try:
            channel = interaction.channel
            if not channel:
                return
            await _get_scheduler(self.bot).schedule_refresh(
                self.bot,
                self.giveaway_id,
                channel=channel,
                message_id=self.message_id,
            )
        except Exception as e:
            logger.warning("Could not update giveaway embed: %s", e)


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: uuid.UUID, bot, entry_count: int = 0):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.bot = bot

        join_btn = discord.ui.Button(
            label="🎉 Join", style=discord.ButtonStyle.primary, custom_id="giveaway:join"
        )
        join_btn.callback = self.join_button
        self.add_item(join_btn)

        entries_label = f"👥 {entry_count}" if entry_count > 0 else "👥"
        entries_btn = discord.ui.Button(
            label=entries_label,
            style=discord.ButtonStyle.secondary,
            custom_id="giveaway:entries",
        )
        entries_btn.callback = self.entries_button
        self.add_item(entries_btn)

    async def join_button(self, interaction: discord.Interaction):
        with trace_span(
            "giveaway.join_button",
            feature="giveaway",
            attributes={
                "discord.guild_id": str(interaction.guild_id),
                "discord.user_id": str(interaction.user.id),
                "discord.message_id": str(interaction.message.id),
            },
        ):
            if not await self._defer_ephemeral(interaction):
                return
            try:
                giveaway = await self._get_giveaway(interaction.message.id)
                if not giveaway:
                    await interaction.followup.send("Giveaway not found.", ephemeral=True)
                    return
                if not giveaway["is_active"]:
                    await interaction.followup.send("This giveaway has ended.", ephemeral=True)
                    return

                ok, reason = await self._check_eligibility(interaction, giveaway)
                if not ok:
                    await interaction.followup.send(reason, ephemeral=True)
                    logger.warning(
                        f"Giveaway eligibility failed: user={interaction.user.id} "
                        f"giveaway={giveaway['id']} reason={reason} "
                        f"required_roles={giveaway.get('required_roles')} "
                        f"(type={type(giveaway.get('required_roles')).__name__})"
                    )
                    return

                entries = self._calculate_entries(interaction.user.roles, giveaway)
                if await self._add_entry(giveaway["id"], interaction.user.id, entries):
                    await self._schedule_embed_update(interaction.message, giveaway["id"])
                    await interaction.followup.send(
                        "You have successfully joined this giveaway.",
                        ephemeral=True,
                    )
                else:
                    view = AlreadyJoinedView(giveaway["id"], interaction.message.id, self.bot)
                    await interaction.followup.send(
                        "🚫 **You have already joined this giveaway!**",
                        ephemeral=True,
                        view=view,
                    )
            except Exception as e:
                logger.error("Join error: %s", e, exc_info=True)
                if self.bot.metrics:
                    self.bot.metrics.errors_total.labels(error_type="giveaway_join").inc()
                await interaction.followup.send("Error joining giveaway.", ephemeral=True)

    async def _defer_ephemeral(self, interaction: discord.Interaction) -> bool:
        try:
            await interaction.response.defer(ephemeral=True)
            return True
        except discord.NotFound:  # pragma: no cover - message deleted before defer
            return False

    async def entries_button(self, interaction: discord.Interaction):
        with trace_span(
            "giveaway.entries_button",
            feature="giveaway",
            attributes={
                "discord.guild_id": str(interaction.guild_id),
                "discord.message_id": str(interaction.message.id),
            },
        ):
            if not await self._defer_ephemeral(interaction):
                return
            try:
                giveaway = await self._get_giveaway(interaction.message.id)
                if not giveaway:
                    await interaction.followup.send("Giveaway not found.", ephemeral=True)
                    return
                rows = await self._get_entries(giveaway["id"])
                if not rows:
                    await interaction.followup.send("No entries yet.", ephemeral=True)
                    return
                view = EntriesPaginatedView(
                    rows,
                    winners_count=giveaway.get("winners_count", 1),
                    user_id=interaction.user.id,
                    timeout=60,
                )
                view._update_buttons()
                await interaction.followup.send(view._format_page(), ephemeral=True, view=view)
            except Exception as e:
                logger.error("Entries error: %s", e, exc_info=True)
                if self.bot.metrics:
                    self.bot.metrics.errors_total.labels(error_type="giveaway_entries").inc()
                await interaction.followup.send("Error fetching entries.", ephemeral=True)

    async def _get_entries(self, giveaway_id: uuid.UUID):
        return await get_repository(self.bot).fetch_entries(giveaway_id, cache=self.bot.cache)

    async def _get_giveaway(self, message_id: int):
        return await get_repository(self.bot).fetch_by_message_id(message_id, cache=self.bot.cache)

    async def _check_eligibility(self, interaction: discord.Interaction, giveaway) -> tuple:
        user_roles = {r.id for r in interaction.user.roles}
        bypass = giveaway.get("bypass_roles") or []
        if any(r in user_roles for r in bypass):
            return True, ""
        if any(r in user_roles for r in (giveaway.get("blacklist_roles") or [])):
            return False, "You have a blacklisted role."
        required = giveaway.get("required_roles") or []
        if required and not any(r in user_roles for r in required):
            return False, "You don't have a required role."
        if giveaway.get("no_donor_win") and interaction.user.id == giveaway.get("donor_id"):
            return False, "Donors cannot win this giveaway."
        return True, ""

    def _calculate_entries(self, roles, giveaway) -> int:
        user_roles = {r.id for r in roles}
        entries = 1
        for role_id_str, bonus in (giveaway.get("bonus_roles") or {}).items():
            if int(role_id_str) in user_roles:
                entries += bonus
        return entries

    async def _add_entry(self, giveaway_id: uuid.UUID, user_id: int, entries: int) -> bool:
        return await get_repository(self.bot).add_entry(
            giveaway_id, user_id, entries, cache=self.bot.cache
        )

    async def _update_embed(self, message: discord.Message, giveaway_id: uuid.UUID):
        await self._refresh_embed_now(message, giveaway_id)

    async def _schedule_embed_update(self, message: discord.Message, giveaway_id: uuid.UUID):
        await _get_scheduler(self.bot).schedule_refresh(
            self.bot,
            giveaway_id,
            message=message,
        )

    async def _refresh_embed_now(self, message: discord.Message, giveaway_id: uuid.UUID):
        giveaway_repo = get_repository(self.bot)
        count = await giveaway_repo.count_entries(giveaway_id)
        giveaway = await giveaway_repo.fetch_by_id(giveaway_id)
        with trace_span(
            "giveaway.refresh_embed",
            feature="giveaway",
            attributes={
                "giveaway.id": str(giveaway_id),
                "discord.message_id": str(message.id),
                "giveaway.entry_count": count or 0,
            },
        ):
            if giveaway:
                try:
                    view = GiveawayView(giveaway_id, self.bot, entry_count=count or 0)
                    await message.edit(embed=build_embed(giveaway, count or 0), view=view)
                except Exception as e:
                    logger.debug("Update embed failed: %s", e)
