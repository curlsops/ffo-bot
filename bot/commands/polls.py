import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin

logger = logging.getLogger(__name__)

POLL_DURATIONS = ["1h", "6h", "1d", "3d", "7d"]


async def _poll_duration_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not current:
        return [app_commands.Choice(name=d, value=d) for d in POLL_DURATIONS]
    cur = current.lower()
    matches = [app_commands.Choice(name=d, value=d) for d in POLL_DURATIONS if cur in d]
    return matches if matches else [app_commands.Choice(name=d, value=d) for d in POLL_DURATIONS]


def _discord_timestamp(dt: datetime, fmt: str = "R") -> str:
    return f"<t:{int(dt.timestamp())}:{fmt}>"


def _parse_duration(s: str) -> timedelta | None:
    m = re.match(r"^(\d+)([mhd])$", s.strip().lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        hours = max(1, n // 60)
    elif unit == "h":
        hours = min(168, max(1, n))
    else:  # d
        hours = min(168, max(24, n * 24))
    return timedelta(hours=hours)


async def _close_reaction_poll_after(
    channel: discord.abc.MessageableChannel,
    message_id: int,
    delta: timedelta,
    opts: list[str],
    emojis: list[str],
    question: str,
) -> None:
    await asyncio.sleep(delta.total_seconds())
    try:
        msg = await channel.fetch_message(message_id)
        reaction_counts = {str(r.emoji): max(0, r.count - 1) for r in msg.reactions}
        result_lines = [
            f"{emojis[i]} {opts[i]} — {reaction_counts.get(emojis[i], 0)}" for i in range(len(opts))
        ]
        description = "\n".join(result_lines) + "\n\n*Poll ended*"
        ended_embed = discord.Embed(
            title=f"📊 {question}",
            description=description,
            color=discord.Color.dark_grey(),
            timestamp=datetime.now(timezone.utc),
        )
        ended_embed.set_footer(text="Poll ended")
        await msg.edit(embed=ended_embed)
        await msg.clear_reactions()
    except Exception as e:
        logger.warning("Failed to close reaction poll: %s", e)


class PollCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _create_long_poll_emojis(self) -> list[str]:
        return [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
            "8️⃣",
            "9️⃣",
            "🔟",
            "🇦",
            "🇧",
            "🇨",
            "🇩",
            "🇪",
            "🇫",
            "🇬",
            "🇭",
            "🇮",
            "🇯",
        ]

    @app_commands.command(name="poll", description="Create a poll")
    @app_commands.guild_only()
    @app_commands.describe(
        question="The poll question (max 300 chars)",
        options="Comma-separated options (2-20). Uses native poll for ≤10, reaction-based for 11+.",
        duration="How long the poll runs: 1h, 6h, 1d, 3d, 7d",
        multi="Allow multiple selections (native poll only)",
        channel="Post to this channel (Admin only; omit to post in current channel)",
    )
    @app_commands.autocomplete(duration=_poll_duration_autocomplete)
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        duration: str = "1d",
        multi: bool = False,
        channel: discord.TextChannel | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            target = channel or interaction.channel
            if channel is not None and not await require_admin(interaction, "poll", self.bot):
                return

            if len(question) > 300:
                await interaction.followup.send(
                    "Question too long (max 300 characters).", ephemeral=True
                )
                return

            raw_opts = [o.strip() for o in options.split(",") if o.strip()]
            if len(raw_opts) < 2:
                await interaction.followup.send(
                    "Need at least 2 options (comma-separated).", ephemeral=True
                )
                return

            use_long = len(raw_opts) > 10
            if use_long:
                opts = [o[:100] for o in raw_opts][:20]
            else:
                opts = [o[:55] for o in raw_opts][:10]

            if use_long:
                delta = _parse_duration(duration)
                if not delta or delta.total_seconds() < 3600:
                    await interaction.followup.send(
                        "Invalid duration. Use 1h, 6h, 1d, 3d, or 7d.", ephemeral=True
                    )
                    return

                emojis = self._create_long_poll_emojis()[: len(opts)]
                lines = [f"{emojis[i]} {opts[i]}" for i in range(len(opts))]
                ends_at = datetime.now(timezone.utc) + delta
                embed = discord.Embed(
                    title=f"📊 {question}",
                    description="\n".join(lines) + "\n\n*React to vote*",
                    color=discord.Color.blue(),
                    timestamp=ends_at,
                )
                embed.set_footer(text=f"Ends {_discord_timestamp(ends_at, 'R')}")
                msg = await target.send(embed=embed)
                for emoji in emojis:
                    await msg.add_reaction(emoji)
                asyncio.create_task(
                    _close_reaction_poll_after(target, msg.id, delta, opts, emojis, question)
                )
                await interaction.followup.send(
                    f"Poll created with {len(opts)} options (reaction-based). React to vote.",
                    ephemeral=True,
                )
            else:
                delta = _parse_duration(duration)
                if not delta or delta.total_seconds() < 3600:
                    await interaction.followup.send(
                        "Invalid duration. Use 1h, 6h, 1d, 3d, or 7d.", ephemeral=True
                    )
                    return

                poll = discord.Poll(question=question, duration=delta, multiple=multi)
                for opt in opts:
                    poll.add_answer(text=opt)

                await target.send(poll=poll)
                await interaction.followup.send("Poll created!", ephemeral=True)
        except Exception as e:
            logger.error("Poll error: %s", e, exc_info=True)
            await interaction.followup.send("Error creating poll.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PollCommands(bot))
