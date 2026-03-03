import logging
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.db import TRANSIENT_DB_ERRORS
from config.constants import Role

logger = logging.getLogger(__name__)

GIVEAWAY_DURATIONS = [
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "6h",
    "12h",
    "1d",
    "2d",
    "3d",
    "5d",
    "7d",
    "1w",
    "2w",
]

TIME_REGEX = re.compile(r"^(\d+)([smhdw])$", re.IGNORECASE)
TIME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(duration: str) -> Optional[int]:
    match = TIME_REGEX.match(duration.strip())
    if not match:
        return None
    return int(match.group(1)) * TIME_UNITS[match.group(2).lower()]


async def _giveaway_duration_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not current:
        return [app_commands.Choice(name=d, value=d) for d in GIVEAWAY_DURATIONS[:25]]
    cur = current.lower()
    matches = [app_commands.Choice(name=d, value=d) for d in GIVEAWAY_DURATIONS if cur in d]
    return (
        matches[:25]
        if matches
        else [app_commands.Choice(name=d, value=d) for d in GIVEAWAY_DURATIONS[:25]]
    )


async def _giveaway_message_id_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    try:
        bot = interaction.client
        async with bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_id, prize, ended_at
                FROM giveaways
                WHERE server_id = $1 AND message_id IS NOT NULL
                ORDER BY ended_at DESC NULLS FIRST
                LIMIT 25
                """,
                interaction.guild_id,
            )
        choices = []
        for r in rows:
            mid = str(r["message_id"])
            prize = (r["prize"][:40] + "…") if len(r["prize"]) > 40 else r["prize"]
            label = f"{mid} — {prize}" + (" (ended)" if r["ended_at"] else "")
            if not current or current in mid or current.lower() in prize.lower():
                choices.append(app_commands.Choice(name=label[:100], value=mid))
        return choices[:25]
    except Exception:
        return []


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
        if w:
            footer = f"{w} {winner_word} • {footer}"
    else:
        ends_str = ends_at.strftime("%b %d at %H:%M")
        footer = f"{w} {winner_word} | Ends {ends_str}"
    embed.set_footer(text=footer)
    if giveaway.get("image_url"):
        embed.set_image(url=giveaway["image_url"])
    return embed


PER_PAGE = 10


class EntriesPaginatedView(discord.ui.View):
    def __init__(self, rows: list, user_id: Optional[int] = None, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.rows = rows
        self.user_id = user_id
        self.page = 0
        self.total_entries = sum(r["entries"] for r in rows)
        self.max_page = max(0, (len(rows) - 1) // PER_PAGE)
        self._user_entry = next((r for r in rows if r["user_id"] == user_id), None)

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id="entries:prev",
            row=0,
        )
        prev_btn.callback = self._prev_callback
        self.add_item(prev_btn)

        self.page_btn = discord.ui.Button(
            label=f"1/{self.max_page + 1}",
            style=discord.ButtonStyle.success,
            custom_id="entries:page",
            disabled=True,
            row=0,
        )
        self.add_item(self.page_btn)

        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id="entries:next",
            row=0,
        )
        next_btn.callback = self._next_callback
        self.add_item(next_btn)

        if self._user_entry is not None:
            my_btn = discord.ui.Button(
                label="✓ My Entry",
                style=discord.ButtonStyle.primary,
                custom_id="entries:mine",
                row=0,
            )
            my_btn.callback = self._my_entry_callback
            self.add_item(my_btn)

    def _format_page(self) -> str:
        start = self.page * PER_PAGE
        chunk = self.rows[start : start + PER_PAGE]
        lines = [f"<@{r['user_id']}>" for r in chunk]
        body = "\n".join(lines)
        return f"**Giveaway Participants**\n\n{body}"

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self.max_page + 1}"
        for child in self.children:
            if child.custom_id == "entries:prev":
                child.disabled = self.page <= 0
            elif child.custom_id == "entries:next":
                child.disabled = self.page >= self.max_page

    async def _prev_callback(self, interaction: discord.Interaction):
        if self.page <= 0:
            return
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(content=self._format_page(), view=self)

    async def _next_callback(self, interaction: discord.Interaction):
        if self.page >= self.max_page:
            return
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(content=self._format_page(), view=self)

    async def _my_entry_callback(self, interaction: discord.Interaction):
        entries = self._user_entry["entries"]
        total = self.total_entries
        pct = (entries / total * 100) if total > 0 else 0
        pct_str = f"{pct:.2f}".rstrip("0").rstrip(".") if pct < 100 else "100"
        lines = [
            f"✓ You had **{entries}** {'entry' if entries == 1 else 'entries'} for this giveaway!",
            f"ℹ️ There are a total of **{total}** entries in this giveaway (including bonuses).",
            f"🎁 Your chances of winning: **{pct_str}%**",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


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
                    "SELECT * FROM giveaways WHERE id = $1", self.giveaway_id
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
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
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

    async def entries_button(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
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
            view = EntriesPaginatedView(rows, user_id=interaction.user.id, timeout=60)
            view._update_buttons()
            await interaction.followup.send(view._format_page(), ephemeral=True, view=view)
        except Exception as e:
            logger.error("Entries error: %s", e, exc_info=True)
            await interaction.followup.send("Error fetching entries.", ephemeral=True)

    async def _get_entries(self, giveaway_id: uuid.UUID):
        cache = self.bot.cache
        cache_key = f"giveaway:entries:{giveaway_id}"
        try:
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id = $1 ORDER BY created_at",
                    giveaway_id,
                )
            if cache:
                cache.set(cache_key, [dict(r) for r in rows], ttl=60)
            return rows
        except TRANSIENT_DB_ERRORS:
            if cache:
                cached = cache.get(cache_key)
                if cached is not None:
                    logger.warning("DB unavailable, using cache")
                    return cached
            raise

    async def _get_giveaway(self, message_id: int):
        cache = self.bot.cache
        cache_key = f"giveaway:msg:{message_id}"
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM giveaways WHERE message_id = $1", message_id
                )
            if row and cache:
                cache.set(cache_key, dict(row), ttl=300)
            return row
        except TRANSIENT_DB_ERRORS:
            if cache:
                cached = cache.get(cache_key)
                if cached is not None:
                    logger.warning("DB unavailable, using cache")
                    return cached
            raise

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
            except Exception:
                return False

    async def _update_embed(self, message: discord.Message, giveaway_id: uuid.UUID):
        async with self.bot.db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = $1", giveaway_id
            )
            giveaway = await conn.fetchrow("SELECT * FROM giveaways WHERE id = $1", giveaway_id)
        if giveaway:
            try:
                view = GiveawayView(giveaway_id, self.bot, entry_count=count or 0)
                await message.edit(embed=build_embed(giveaway, count or 0), view=view)
            except Exception:
                pass


class GiveawayCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("Admin required.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="gstart", description="Start a giveaway")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(duration=_giveaway_duration_autocomplete)
    @app_commands.describe(
        duration="Duration (e.g. 1h, 2d, 1w)",
        winners="Number of winners",
        prize="Prize description",
        donor="User who donated the prize",
        required_roles="Comma-separated role mentions required to enter",
        blacklist_roles="Comma-separated role mentions blocked from entering",
        bypass_roles="Comma-separated role mentions that bypass requirements",
        bonus_roles="Format: @role:entries,@role:entries",
        messages="Required messages: count,#channel",
        nodonorwin="Prevent donor from winning",
        ping="Ping @everyone when starting",
        nodefaults="Disable server default settings",
        extra_text="Additional text to display",
        image="Image URL to display",
    )
    async def gstart(
        self,
        interaction: discord.Interaction,
        duration: str,
        winners: int,
        prize: str,
        donor: Optional[discord.Member] = None,
        required_roles: Optional[str] = None,
        blacklist_roles: Optional[str] = None,
        bypass_roles: Optional[str] = None,
        bonus_roles: Optional[str] = None,
        messages: Optional[str] = None,
        nodonorwin: bool = False,
        ping: bool = False,
        nodefaults: bool = False,
        extra_text: Optional[str] = None,
        image: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            if not await self._check_admin(interaction, "gstart"):
                return

            seconds = parse_duration(duration)
            if not seconds or seconds < 60:
                await interaction.followup.send(
                    "Invalid duration. Min 1m. Examples: 1h, 2d, 1w", ephemeral=True
                )
                return
            if winners < 1 or winners > 50:
                await interaction.followup.send("Winners must be 1-50.", ephemeral=True)
                return
            if len(prize) > 500:
                await interaction.followup.send("Prize max 500 chars.", ephemeral=True)
                return

            ends_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            giveaway_id = uuid.uuid4()
            giveaway_data = {
                "prize": prize,
                "host_id": interaction.user.id,
                "donor_id": donor.id if donor else None,
                "winners_count": winners,
                "ends_at": ends_at,
                "extra_text": extra_text,
                "image_url": image,
            }

            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO giveaways (id, server_id, channel_id, host_id, donor_id,
                       prize, winners_count, ends_at, required_roles, blacklist_roles,
                       bypass_roles, bonus_roles, message_req, no_donor_win, no_defaults,
                       ping, extra_text, image_url)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)""",
                    giveaway_id,
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                    donor.id if donor else None,
                    prize,
                    winners,
                    ends_at,
                    self._parse_roles(required_roles),
                    self._parse_roles(blacklist_roles),
                    self._parse_roles(bypass_roles),
                    self._parse_bonus_roles(bonus_roles),
                    self._parse_messages(messages),
                    nodonorwin,
                    nodefaults,
                    ping,
                    extra_text,
                    image,
                )

            view = GiveawayView(giveaway_id, self.bot, entry_count=0)
            msg = await interaction.followup.send(
                content="@everyone" if ping else None,
                embed=build_embed(giveaway_data, 0),
                view=view,
            )

            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE giveaways SET message_id = $1 WHERE id = $2", msg.id, giveaway_id
                )

            if self.bot.metrics:
                self.bot.metrics.commands_executed.labels(
                    command_name="gstart", server_id=str(interaction.guild_id), status="success"
                ).inc()

            if self.bot.notifier:
                await self.bot.notifier.notify_giveaway_created(
                    interaction.guild_id,
                    prize,
                    interaction.user.id,
                    interaction.channel_id,
                    ends_at,
                )
        except Exception as e:
            logger.error("gstart error: %s", e, exc_info=True)
            await interaction.followup.send("Error starting giveaway.", ephemeral=True)

    @app_commands.command(name="greroll", description="Reroll winners for an ended giveaway")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(message_id=_giveaway_message_id_autocomplete)
    @app_commands.describe(
        message_id="The giveaway message ID (from the message link, or right-click → Copy ID)",
        count="Number of winners to reroll (default: all). Use when some winners didn't claim.",
    )
    async def greroll(
        self, interaction: discord.Interaction, message_id: str, count: Optional[int] = None
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self._check_admin(interaction, "greroll"):
                return

            msg_id = self._parse_message_id(message_id)
            if not msg_id:
                await interaction.followup.send(
                    "Invalid message ID. Use the number from the message link or enable Developer Mode and right-click → Copy Message Link.",
                    ephemeral=True,
                )
                return

            async with self.bot.db_pool.acquire() as conn:
                giveaway = await conn.fetchrow(
                    "SELECT * FROM giveaways WHERE message_id = $1", msg_id
                )
            if not giveaway:
                await interaction.followup.send("Giveaway not found.", ephemeral=True)
                return
            if giveaway["is_active"]:
                await interaction.followup.send(
                    "Giveaway is still active. Reroll only works for ended giveaways.",
                    ephemeral=True,
                )
                return

            async with self.bot.db_pool.acquire() as conn:
                entries = await conn.fetch(
                    "SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id = $1",
                    giveaway["id"],
                )
                old_winners = await conn.fetch(
                    "SELECT user_id FROM giveaway_entries WHERE giveaway_id = $1 AND is_winner = true",
                    giveaway["id"],
                )

            if not entries:
                await interaction.followup.send("No entries to reroll from.", ephemeral=True)
                return

            old_winner_ids = {r["user_id"] for r in old_winners}
            default_reroll_count = len(old_winner_ids) or giveaway["winners_count"]
            reroll_count = default_reroll_count if count is None else count
            if reroll_count < 1:
                await interaction.followup.send("Count must be at least 1.", ephemeral=True)
                return
            if old_winner_ids and reroll_count > len(old_winner_ids):
                await interaction.followup.send(
                    f"Cannot reroll more than {len(old_winner_ids)} winner(s).",
                    ephemeral=True,
                )
                return

            if reroll_count < len(old_winner_ids):
                winners_to_remove = set(random.sample(list(old_winner_ids), reroll_count))
            else:
                winners_to_remove = old_winner_ids
            non_winners = [e for e in entries if e["user_id"] not in old_winner_ids]
            if not non_winners:
                await interaction.followup.send(
                    "All entrants were winners. No one left to reroll.",
                    ephemeral=True,
                )
                return
            pool = non_winners + [e for e in entries if e["user_id"] in winners_to_remove]
            new_winners = self._select_winners(pool, reroll_count)
            final_winners = (old_winner_ids - winners_to_remove) | set(new_winners)

            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE giveaway_entries SET is_winner = false WHERE giveaway_id = $1",
                    giveaway["id"],
                )
                if final_winners:
                    await conn.executemany(
                        "UPDATE giveaway_entries SET is_winner = true WHERE giveaway_id = $1 AND user_id = $2",
                        [(giveaway["id"], w) for w in final_winners],
                    )

            channel = self.bot.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(giveaway["message_id"])
                    embed = build_embed(dict(giveaway), len(entries), ended=True)
                    if new_winners:
                        embed.add_field(
                            name="Winners (Rerolled)",
                            value="\n".join(f"<@{w}>" for w in new_winners),
                            inline=False,
                        )
                    await msg.edit(embed=embed)
                except discord.NotFound:
                    pass

                if new_winners:
                    mentions = " ".join(f"<@{w}>" for w in new_winners)
                    await channel.send(
                        f"🎉 Reroll! New winners for **{giveaway['prize']}**: {mentions}"
                    )
                else:
                    await channel.send(f"Reroll for **{giveaway['prize']}** — no valid entries.")

            await interaction.followup.send(
                f"Rerolled! New winner(s): {', '.join(f'<@{w}>' for w in new_winners) if new_winners else 'None'}",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("greroll error: %s", e, exc_info=True)
            await interaction.followup.send("Error rerolling giveaway.", ephemeral=True)

    def _parse_message_id(self, s: str) -> Optional[int]:
        s = s.strip()
        m = re.search(r"/(\d{17,20})$", s)
        if m:
            return int(m.group(1))
        if s.isdigit():
            return int(s)
        return None

    def _select_winners(self, entries: list, count: int) -> list:
        if not entries or count < 1:
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

    def _parse_roles(self, roles_str: Optional[str]) -> list:
        if not roles_str:
            return []
        return [int(m.group(1)) for m in re.finditer(r"<@&(\d+)>", roles_str)]

    def _parse_bonus_roles(self, bonus_str: Optional[str]) -> dict:
        if not bonus_str:
            return {}
        bonus = {}
        for part in bonus_str.split(","):
            m = re.match(r"<@&(\d+)>:(\d+)", part.strip())
            if m:
                bonus[m.group(1)] = int(m.group(2))
        return bonus

    def _parse_messages(self, messages_str: Optional[str]) -> Optional[dict]:
        if not messages_str:
            return None
        parts = messages_str.split(",")
        if len(parts) != 2:
            return None
        try:
            count = int(parts[0].strip())
            m = re.match(r"<#(\d+)>", parts[1].strip())
            if m:
                return {"count": count, "channel_id": int(m.group(1))}
        except ValueError:
            pass
        return None


async def setup(bot):
    await bot.add_cog(GiveawayCommands(bot))
