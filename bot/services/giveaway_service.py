import logging

import discord

from bot.utils.discord_helpers import discord_timestamp, get_or_fetch_channel
from bot.utils.giveaway_selection import select_weighted_winners
from bot.utils.telemetry import trace_span

logger = logging.getLogger(__name__)


def select_winners(entries: list, count: int) -> list:
    return select_weighted_winners(entries, count)


def format_winner_mentions(winners: list[int]) -> str:
    return " ".join(f"<@{winner_id}>" for winner_id in winners)


def build_end_announcement(prize: str, winners: list[int]) -> str:
    if winners:
        mentions = format_winner_mentions(winners)
        return f"🎉 Congratulations {mentions}! You won **{prize}**!"
    return f"No entries for **{prize}**. No winners."


def build_reroll_announcement(prize: str, winners: list[int]) -> str:
    if winners:
        mentions = format_winner_mentions(winners)
        return f"🎉 Reroll! New winners for **{prize}**: {mentions}"
    return f"Reroll for **{prize}** — no valid entries."


def build_embed(giveaway, entry_count: int, ended: bool = False) -> discord.Embed:
    ends_at = giveaway.get("ended_at") or giveaway["ends_at"]
    ts_rel = discord_timestamp(ends_at, "R")
    ts_full = discord_timestamp(ends_at, "F")

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
    winners_count = giveaway.get("winners_count") or 1
    winner_word = "winner" if winners_count == 1 else "winners"
    entry_word = "entry" if entry_count == 1 else "entries"
    if ended:
        footer = f"{entry_count} {entry_word}"
        if winners_count:  # pragma: no branch - winners_count is always >= 1 due to "or 1"
            footer = f"{winners_count} {winner_word} • {footer}"
    else:
        ends_str = ends_at.strftime("%b %d at %H:%M")
        footer = f"{winners_count} {winner_word} | Ends {ends_str}"
    embed.set_footer(text=footer)
    if giveaway.get("image_url"):
        embed.set_image(url=giveaway["image_url"])
    return embed


def build_ended_embed(giveaway, winners: list[int], entry_count: int) -> discord.Embed:
    ended_at = giveaway["ended_at"]
    ts_full = discord_timestamp(ended_at, "F")

    lines = [
        f"**{giveaway['prize']}**",
        "",
        f"**Ended:** {ts_full}",
        f"**Hosted by:** <@{giveaway['host_id']}>",
    ]
    if giveaway.get("donor_id"):
        lines.append(f"**Donated by:** <@{giveaway['donor_id']}>")

    embed = discord.Embed(
        title="🎉 GIVEAWAY ENDED 🎉",
        description="\n".join(lines),
        color=discord.Color.dark_grey(),
        timestamp=ended_at,
    )
    if winners:
        embed.add_field(
            name="Winners",
            value="\n".join(f"<@{winner_id}>" for winner_id in winners),
            inline=False,
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


async def finalize_and_announce(
    bot, giveaway: dict, winners: list[int], entry_count: int, announcement: str
):
    with trace_span(
        "giveaway.finalize_and_announce",
        feature="giveaway",
        attributes={
            "discord.channel_id": str(giveaway["channel_id"]),
            "giveaway.id": str(giveaway["id"]),
        },
    ):
        channel = await get_or_fetch_channel(bot, giveaway["channel_id"])
        if not channel:
            logger.warning(
                "Could not fetch channel %s for giveaway %s",
                giveaway["channel_id"],
                giveaway["id"],
            )
            return None
        try:
            msg = await channel.fetch_message(giveaway["message_id"])  # type: ignore[attr-defined]
            await msg.edit(embed=build_ended_embed(giveaway, winners, entry_count), view=None)
        except discord.NotFound:
            pass
        await channel.send(announcement)  # type: ignore[attr-defined]
        return channel
