import logging
import re
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role

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


def _parse_duration(s: str) -> Optional[timedelta]:
    m = re.match(r"^(\d+)([mhd])$", s.strip().lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        hours = max(1, n // 60)
    elif unit == "h":
        hours = min(168, max(1, n))  # 1h to 7 days
    else:  # d
        hours = min(168, max(24, n * 24))
    return timedelta(hours=hours)


class PollCommands(commands.Cog):
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

    @app_commands.command(name="poll", description="Create a poll (Admin only)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        question="The poll question (max 300 chars)",
        options="Comma-separated options (2-10, max 55 chars each). E.g. Yes,No,Maybe",
        duration="How long the poll runs: 1h, 6h, 1d, 3d, 7d (default: 1d)",
        multi="Allow multiple selections",
    )
    @app_commands.autocomplete(duration=_poll_duration_autocomplete)
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        duration: str = "1d",
        multi: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self._check_admin(interaction, "poll"):
                return

            if len(question) > 300:
                await interaction.followup.send(
                    "Question too long (max 300 characters).", ephemeral=True
                )
                return

            opts = [o.strip()[:55] for o in options.split(",") if o.strip()][:10]
            if len(opts) < 2:
                await interaction.followup.send(
                    "Need at least 2 options (comma-separated).", ephemeral=True
                )
                return

            delta = _parse_duration(duration)
            if not delta or delta.total_seconds() < 3600:
                await interaction.followup.send(
                    "Invalid duration. Use 1h, 6h, 1d, 3d, or 7d.", ephemeral=True
                )
                return

            poll = discord.Poll(question=question, duration=delta, multiple=multi)
            for opt in opts:
                poll.add_answer(text=opt)

            await interaction.channel.send(poll=poll)
            await interaction.followup.send("Poll created!", ephemeral=True)
        except Exception as e:
            logger.error("Poll error: %s", e, exc_info=True)
            await interaction.followup.send("Error creating poll.", ephemeral=True)

    @app_commands.command(
        name="poll_long",
        description="Create a poll with up to 20 options (reaction-based, Admin only)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        question="The poll question (max 300 chars)",
        options="Comma-separated options (2-20). E.g. A,B,C,D,E,F,G,H,I,J,K",
    )
    async def poll_long(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self._check_admin(interaction, "poll_long"):
                return

            if len(question) > 300:
                await interaction.followup.send(
                    "Question too long (max 300 characters).", ephemeral=True
                )
                return

            opts = [o.strip()[:100] for o in options.split(",") if o.strip()][:20]
            if len(opts) < 2:
                await interaction.followup.send(
                    "Need at least 2 options (comma-separated).", ephemeral=True
                )
                return

            # 1️⃣-9️⃣, 0️⃣(10), A-J for 11-20
            num_emoji = [
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
            emojis = num_emoji[: len(opts)]

            lines = [f"{emojis[i]} {opts[i]}" for i in range(len(opts))]
            embed = discord.Embed(
                title=f"📊 {question}",
                description="\n".join(lines) + "\n\n*React to vote*",
                color=discord.Color.blue(),
            )
            msg = await interaction.channel.send(embed=embed)
            for emoji in emojis:
                await msg.add_reaction(emoji)

            await interaction.followup.send("Long poll created! React to vote.", ephemeral=True)
        except Exception as e:
            logger.error("poll_long error: %s", e, exc_info=True)
            await interaction.followup.send("Error creating poll.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PollCommands(bot))
