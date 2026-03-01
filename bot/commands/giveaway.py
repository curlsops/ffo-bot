import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role

logger = logging.getLogger(__name__)

TIME_REGEX = re.compile(r"^(\d+)([smhdw])$", re.IGNORECASE)
TIME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(duration: str) -> Optional[int]:
    match = TIME_REGEX.match(duration.strip())
    if not match:
        return None
    return int(match.group(1)) * TIME_UNITS[match.group(2).lower()]


def format_time_remaining(ends_at: datetime) -> str:
    delta = ends_at - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return "Ended"
    d, r = divmod(int(delta.total_seconds()), 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m or not parts:
        parts.append(f"{m}m")
    return " ".join(parts)


def build_embed(giveaway, entry_count: int, ended: bool = False) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 GIVEAWAY ENDED 🎉" if ended else "🎉 GIVEAWAY 🎉",
        description=f"**{giveaway['prize']}**",
        color=discord.Color.dark_grey() if ended else discord.Color.gold(),
        timestamp=giveaway.get("ended_at") or giveaway["ends_at"],
    )
    donor = f"<@{giveaway['donor_id']}>" if giveaway.get("donor_id") else "N/A"
    embed.add_field(name="Hosted by", value=f"<@{giveaway['host_id']}>", inline=True)
    embed.add_field(name="Donated by", value=donor, inline=True)
    if ended:
        embed.add_field(name="Total Entries", value=str(entry_count), inline=True)
    else:
        embed.add_field(name="Winners", value=str(giveaway["winners_count"]), inline=True)
        embed.add_field(name="Entries", value=str(entry_count), inline=True)
        embed.add_field(
            name="Time Remaining", value=format_time_remaining(giveaway["ends_at"]), inline=True
        )
    if giveaway.get("extra_text"):
        embed.add_field(name="Info", value=giveaway["extra_text"], inline=False)
    if giveaway.get("image_url"):
        embed.set_image(url=giveaway["image_url"])
    embed.set_footer(text="Ended at" if ended else "Ends at")
    return embed


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: uuid.UUID, bot):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.bot = bot

    @discord.ui.button(
        label="🎉 Join", style=discord.ButtonStyle.primary, custom_id="giveaway:join"
    )
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
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
                return

            entries = self._calculate_entries(interaction.user.roles, giveaway)
            if await self._add_entry(giveaway["id"], interaction.user.id, entries):
                await self._update_embed(interaction.message, giveaway["id"])
                await interaction.followup.send(
                    f"You joined with **{entries}** {'entries' if entries > 1 else 'entry'}!",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send("You've already joined!", ephemeral=True)
        except Exception as e:
            logger.error(f"Join error: {e}", exc_info=True)
            await interaction.followup.send("Error joining giveaway.", ephemeral=True)

    async def _get_giveaway(self, message_id: int):
        async with self.bot.db_pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM giveaways WHERE message_id = $1", message_id)

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
                await message.edit(embed=build_embed(giveaway, count))
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

            view = GiveawayView(giveaway_id, self.bot)
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
            logger.error(f"gstart error: {e}", exc_info=True)
            await interaction.followup.send("Error starting giveaway.", ephemeral=True)

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
