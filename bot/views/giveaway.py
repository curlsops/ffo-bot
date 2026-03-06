import logging
import uuid
from datetime import datetime

import discord

from bot.utils.db import cached_or_fallback
from bot.utils.pagination import ListPaginatedView

logger = logging.getLogger(__name__)

GIVEAWAY_COLUMNS = (
    "id, server_id, channel_id, message_id, host_id, donor_id, prize, winners_count, "
    "ends_at, started_at, ended_at, required_roles, blacklist_roles, bypass_roles, "
    "bonus_roles, message_req, no_donor_win, no_defaults, ping, extra_text, image_url, "
    "is_active, created_at, updated_at"
)


def _discord_timestamp(dt: datetime, fmt: str = "R") -> str:
    return f"<t:{int(dt.timestamp())}:{fmt}>"


def build_embed(giveaway, entry_count: int, ended: bool = False) -> discord.Embed:
    ends_at = giveaway.get("ended_at") or giveaway["ends_at"]
    ts_rel = _discord_timestamp(ends_at, "R")
    ts_full = _discord_timestamp(ends_at, "F")

    lines = [
        f"**{giveaway['prize']}**",
        "Click join button below to enter!" if not ended else "",
        f"**Ends:** {ts_rel} ({ts_full})" if not ended else f"**Ended:** {ts_full}",
        f"**Hosted by:** <@{giveaway['host_id']}>",
    ]
    if giveaway.get("donor_id"):
        lines.append(f"**Donated by:** <@{giveaway['donor_id']}>")
    if giveaway.get("extra_text"):
        lines.append("")
        lines.append(giveaway["extra_text"])
    description = "\n".join(line for line in lines if line).strip()

    embed = discord.Embed(
        title="🎉 GIVEAWAY ENDED 🎉" if ended else "🎉 GIVEAWAY 🎉",
        description=description,
        color=discord.Color.dark_grey() if ended else discord.Color.gold(),
        timestamp=ends_at if ended else None,
    )
    w = giveaway.get("winners_count") or 1
    winner_word = "winner" if w == 1 else "winners"
    entry_word = "entry" if entry_count == 1 else "entries"
    if ended:
        footer = f"{entry_count} {entry_word}"
        if w:  # pragma: no branch - w is always >= 1 due to "or 1" above
            footer = f"{w} {winner_word} • {footer}"
    else:
        ends_str = ends_at.strftime("%b %d at %H:%M")
        footer = f"{w} {winner_word} | Ends {ends_str}"
    embed.set_footer(text=footer)
    if giveaway.get("image_url"):
        embed.set_image(url=giveaway["image_url"])
    return embed


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
        await interaction.response.defer(ephemeral=True)
        try:
            removed = await self._remove_entry(interaction)
            if removed:
                await self._update_giveaway_embed(interaction)
                await interaction.followup.send(
                    "Your entry for this giveaway has been removed.", ephemeral=True
                )
            else:
                await interaction.followup.send("You are not in this giveaway.", ephemeral=True)
        except Exception as e:
            logger.error("Leave giveaway error: %s", e, exc_info=True)
            await interaction.followup.send("Error leaving giveaway.", ephemeral=True)

    async def _remove_entry(self, interaction: discord.Interaction) -> bool:
        async with self.bot.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM giveaway_entries WHERE giveaway_id = $1 AND user_id = $2",
                self.giveaway_id,
                interaction.user.id,
            )
        return result and "DELETE 1" in result

    async def _update_giveaway_embed(self, interaction: discord.Interaction):
        try:
            channel = interaction.channel
            if not channel:
                return
            msg = await channel.fetch_message(self.message_id)
            async with self.bot.db_pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = $1", self.giveaway_id
                )
                giveaway = await conn.fetchrow(
                    "SELECT " + GIVEAWAY_COLUMNS + " FROM giveaways WHERE id = $1", self.giveaway_id
                )
            if giveaway:
                view = GiveawayView(self.giveaway_id, self.bot, entry_count=count or 0)
                await msg.edit(embed=build_embed(giveaway, count or 0), view=view)
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
                    f"required_roles={giveaway.get('required_roles')} (type={type(giveaway.get('required_roles')).__name__})"
                )
                return

            entries = self._calculate_entries(interaction.user.roles, giveaway)
            if await self._add_entry(giveaway["id"], interaction.user.id, entries):
                if self.bot.cache:
                    self.bot.cache.delete(f"giveaway:entries:{giveaway['id']}")
                await self._update_embed(interaction.message, giveaway["id"])
                await interaction.followup.send(
                    "You have successfully joined this giveaway.", ephemeral=True
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
            await interaction.followup.send("Error joining giveaway.", ephemeral=True)

    async def _defer_ephemeral(self, interaction: discord.Interaction) -> bool:
        try:
            await interaction.response.defer(ephemeral=True)
            return True
        except discord.NotFound:  # pragma: no cover - message deleted before defer
            return False

    async def entries_button(self, interaction: discord.Interaction):
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
            await interaction.followup.send("Error fetching entries.", ephemeral=True)

    async def _get_entries(self, giveaway_id: uuid.UUID):
        async def fetch():
            async with self.bot.db_pool.acquire() as conn:
                return await conn.fetch(
                    "SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id = $1 ORDER BY created_at",
                    giveaway_id,
                )

        return await cached_or_fallback(
            self.bot.cache,
            f"giveaway:entries:{giveaway_id}",
            fetch,
            60,
            lambda r: [dict(x) for x in r],
        )

    async def _get_giveaway(self, message_id: int):
        async def fetch():
            async with self.bot.db_pool.acquire() as conn:
                return await conn.fetchrow(
                    "SELECT " + GIVEAWAY_COLUMNS + " FROM giveaways WHERE message_id = $1",
                    message_id,
                )

        return await cached_or_fallback(
            self.bot.cache,
            f"giveaway:msg:{message_id}",
            fetch,
            300,
            lambda r: dict(r) if r else None,
        )

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
        async with self.bot.db_pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO giveaway_entries (giveaway_id, user_id, entries) VALUES ($1,$2,$3)",
                    giveaway_id,
                    user_id,
                    entries,
                )
                return True
            except Exception as e:
                logger.debug("Add entry failed: %s", e)
                return False

    async def _update_embed(self, message: discord.Message, giveaway_id: uuid.UUID):
        async with self.bot.db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = $1", giveaway_id
            )
            giveaway = await conn.fetchrow(
                "SELECT " + GIVEAWAY_COLUMNS + " FROM giveaways WHERE id = $1", giveaway_id
            )
        if giveaway:
            try:
                view = GiveawayView(giveaway_id, self.bot, entry_count=count or 0)
                await message.edit(embed=build_embed(giveaway, count or 0), view=view)
            except Exception as e:
                logger.debug("Update embed failed: %s", e)
