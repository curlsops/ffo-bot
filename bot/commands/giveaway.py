import logging
import random
import re
import uuid
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, send_error
from bot.utils.autocomplete import cached_autocomplete
from bot.views.giveaway import GIVEAWAY_COLUMNS, GiveawayView, build_embed
from config.constants import Constants

logger = logging.getLogger(__name__)

CACHE_GIVEAWAY_MESSAGE_ID = "giveaway_message_autocomplete:{server_id}"

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

GIVEAWAY_OPERATION_CHOICES = [
    app_commands.Choice(name="Start", value="start"),
    app_commands.Choice(name="Reroll", value="reroll"),
]

TIME_REGEX = re.compile(r"^(\d+)([smhdw])$", re.IGNORECASE)
TIME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(duration: str) -> int | None:
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


async def _fetch_giveaway_message_ids(pool, guild_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT message_id, prize, ended_at
            FROM giveaways
            WHERE server_id = $1 AND message_id IS NOT NULL
            ORDER BY ended_at DESC NULLS FIRST
            LIMIT 25
            """,
            guild_id,
        )


def _giveaway_message_ids_to_choices(
    rows: list[dict], current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    for r in rows:
        mid = str(r["message_id"])
        prize = (r["prize"][:40] + "…") if len(r["prize"]) > 40 else r["prize"]
        label = f"{mid} — {prize}" + (" (ended)" if r["ended_at"] else "")
        if not current or current in mid or current.lower() in prize.lower():
            choices.append(app_commands.Choice(name=label[:100], value=mid))
    return choices


async def _giveaway_message_id_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return await cached_autocomplete(
        interaction,
        current,
        CACHE_GIVEAWAY_MESSAGE_ID,
        _fetch_giveaway_message_ids,
        _giveaway_message_ids_to_choices,
        ttl=Constants.CACHE_TTL,
        log_prefix="Giveaway message",
    )


def _giveaway_command(cog: "GiveawayCommands"):
    @app_commands.command(
        name="giveaway",
        description="Giveaway management. Provide operation.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(operation=GIVEAWAY_OPERATION_CHOICES)
    @app_commands.autocomplete(duration=_giveaway_duration_autocomplete)
    @app_commands.autocomplete(message_id=_giveaway_message_id_autocomplete)
    @app_commands.describe(
        operation="Start a giveaway or reroll winners",
        duration="Duration (Start only, e.g. 1h, 2d, 1w)",
        winners="Number of winners (Start only)",
        prize="Prize description (Start only)",
        message_id="Giveaway message ID (Reroll only)",
        count="Winners to reroll (Reroll only, default: all)",
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
    async def giveaway_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
        duration: str | None = None,
        winners: int | None = None,
        prize: str | None = None,
        message_id: str | None = None,
        count: int | None = None,
        donor: discord.Member | None = None,
        required_roles: str | None = None,
        blacklist_roles: str | None = None,
        bypass_roles: str | None = None,
        bonus_roles: str | None = None,
        messages: str | None = None,
        nodonorwin: bool = False,
        ping: bool = False,
        nodefaults: bool = False,
        extra_text: str | None = None,
        image: str | None = None,
    ):
        if operation.value == "start":
            await _giveaway_start(
                cog,
                interaction,
                duration,
                winners,
                prize,
                donor,
                required_roles,
                blacklist_roles,
                bypass_roles,
                bonus_roles,
                messages,
                nodonorwin,
                ping,
                nodefaults,
                extra_text,
                image,
            )
        else:
            await _giveaway_reroll(cog, interaction, message_id, count)

    return giveaway_cmd


async def _giveaway_start(
    cog: "GiveawayCommands",
    interaction: discord.Interaction,
    duration: str | None,
    winners: int | None,
    prize: str | None,
    donor: discord.Member | None,
    required_roles: str | None,
    blacklist_roles: str | None,
    bypass_roles: str | None,
    bonus_roles: str | None,
    messages: str | None,
    nodonorwin: bool,
    ping: bool,
    nodefaults: bool,
    extra_text: str | None,
    image: str | None,
):
    await interaction.response.defer()
    try:
        if not await require_admin(interaction, "giveaway", cog.bot):
            return
        if not duration or winners is None or not prize:
            await send_error(
                interaction,
                "Duration, winners, and prize required for Start.",
            )
            return

        seconds = parse_duration(duration)
        if not seconds or seconds < 60:
            await send_error(interaction, "Invalid duration. Min 1m. Examples: 1h, 2d, 1w")
            return
        if winners < 1 or winners > 50:
            await send_error(interaction, "Winners must be 1-50.")
            return
        if len(prize) > 500:
            await send_error(interaction, "Prize max 500 chars.")
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

        async with cog.bot.db_pool.acquire() as conn:
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
                cog._parse_roles(required_roles),
                cog._parse_roles(blacklist_roles),
                cog._parse_roles(bypass_roles),
                cog._parse_bonus_roles(bonus_roles),
                cog._parse_messages(messages),
                nodonorwin,
                nodefaults,
                ping,
                extra_text,
                image,
            )

        view = GiveawayView(giveaway_id, cog.bot, entry_count=0)
        msg = await interaction.followup.send(
            content="@everyone" if ping else None,
            embed=build_embed(giveaway_data, 0),
            view=view,
        )

        async with cog.bot.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE giveaways SET message_id = $1 WHERE id = $2", msg.id, giveaway_id
            )

        if cog.bot.cache:
            cog.bot.cache.delete(CACHE_GIVEAWAY_MESSAGE_ID.format(server_id=interaction.guild_id))

        if cog.bot.metrics:
            cog.bot.metrics.commands_executed.labels(
                command_name="giveaway start",
                server_id=str(interaction.guild_id),
                status="success",
            ).inc()

        if cog.bot.notifier:
            await cog.bot.notifier.notify_giveaway_created(
                interaction.guild_id,
                prize,
                interaction.user.id,
                interaction.channel_id,
                ends_at,
            )
    except Exception as e:
        logger.error("giveaway start error: %s", e, exc_info=True)
        await send_error(interaction, "Error starting giveaway.")


async def _giveaway_reroll(
    cog: "GiveawayCommands",
    interaction: discord.Interaction,
    message_id: str | None,
    count: int | None,
):
    await interaction.response.defer(ephemeral=True)
    try:
        if not await require_admin(interaction, "giveaway", cog.bot):
            return
        if not message_id:
            await send_error(interaction, "Message ID required for Reroll.")
            return

        msg_id = cog._parse_message_id(message_id)
        if not msg_id:
            await send_error(
                interaction,
                "Invalid message ID. Use the number from the message link or enable Developer Mode and right-click → Copy Message Link.",
            )
            return

        async with cog.bot.db_pool.acquire() as conn:
            giveaway = await conn.fetchrow(
                "SELECT " + GIVEAWAY_COLUMNS + " FROM giveaways WHERE message_id = $1",
                msg_id,
            )
        if not giveaway:
            await send_error(interaction, "Giveaway not found.")
            return
        if giveaway["is_active"]:
            await send_error(
                interaction,
                "Giveaway is still active. Reroll only works for ended giveaways.",
            )
            return

        async with cog.bot.db_pool.acquire() as conn:
            entries = await conn.fetch(
                "SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id = $1",
                giveaway["id"],
            )
            old_winners = await conn.fetch(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id = $1 AND is_winner = true",
                giveaway["id"],
            )

        if not entries:
            await send_error(interaction, "No entries to reroll from.")
            return

        old_winner_ids = {r["user_id"] for r in old_winners}
        default_reroll_count = len(old_winner_ids) or giveaway["winners_count"]
        reroll_count = default_reroll_count if count is None else count
        if reroll_count < 1:
            await send_error(interaction, "Count must be at least 1.")
            return
        if old_winner_ids and reroll_count > len(old_winner_ids):
            await send_error(
                interaction,
                f"Cannot reroll more than {len(old_winner_ids)} winner(s).",
            )
            return

        if reroll_count < len(old_winner_ids):
            winners_to_remove = set(random.sample(list(old_winner_ids), reroll_count))
        else:
            winners_to_remove = old_winner_ids
        non_winners = [e for e in entries if e["user_id"] not in old_winner_ids]
        if not non_winners:
            await send_error(
                interaction,
                "All entrants were winners. No one left to reroll.",
            )
            return
        new_winners = cog._select_winners(non_winners, reroll_count)
        final_winners = (old_winner_ids - winners_to_remove) | set(new_winners)

        async with cog.bot.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE giveaway_entries SET is_winner = false WHERE giveaway_id = $1",
                giveaway["id"],
            )
            if final_winners:
                await conn.executemany(
                    "UPDATE giveaway_entries SET is_winner = true WHERE giveaway_id = $1 AND user_id = $2",
                    [(giveaway["id"], w) for w in final_winners],
                )

        channel = cog.bot.get_channel(giveaway["channel_id"])
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
        logger.error("giveaway reroll error: %s", e, exc_info=True)
        await send_error(interaction, "Error rerolling giveaway.")


class GiveawayCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_cmd = _giveaway_command(self)

    def _parse_message_id(self, s: str) -> int | None:
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

    def _parse_roles(self, roles_str: str | None) -> list:
        if not roles_str:
            return []
        return [int(m.group(1)) for m in re.finditer(r"<@&(\d+)>", roles_str)]

    def _parse_bonus_roles(self, bonus_str: str | None) -> dict:
        if not bonus_str:
            return {}
        bonus = {}
        for part in bonus_str.split(","):
            m = re.match(r"<@&(\d+)>:(\d+)", part.strip())
            if m:
                bonus[m.group(1)] = int(m.group(2))
        return bonus

    def _parse_messages(self, messages_str: str | None) -> dict | None:
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

    async def cog_load(self):
        self.bot.tree.add_command(self.giveaway_cmd)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.giveaway_cmd.name)


async def setup(bot):
    await bot.add_cog(GiveawayCommands(bot))
