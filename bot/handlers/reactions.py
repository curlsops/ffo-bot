import logging

import discord
from discord.ext import commands

from bot.services.whitelist import ResolutionOutcome
from bot.utils.discord_helpers import get_or_fetch_channel
from bot.utils.telemetry import trace_span
from config.constants import Constants

logger = logging.getLogger(__name__)


class ReactionHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if await self._handle_whitelist_reaction(payload):
            return

        role_id = await self._get_reaction_role(
            payload.guild_id, payload.message_id, str(payload.emoji)
        )
        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(role_id) if guild else None

        if not member or not role:
            return

        try:
            with trace_span(
                "reactions.role_grant",
                attributes={
                    "discord.guild_id": str(payload.guild_id),
                    "discord.role_id": str(role_id),
                },
            ):
                await member.add_roles(role, reason="Reaction role")
        except discord.HTTPException as e:
            logger.error("Failed to assign role: %s", e)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_assignment").inc()

    async def _handle_whitelist_reaction(self, payload: discord.RawReactionActionEvent) -> bool:
        if not payload.guild_id or not getattr(
            self.bot.settings, "feature_minecraft_whitelist", False
        ):
            return False

        svc = self.bot.whitelist_service
        emoji_str = str(payload.emoji)
        if emoji_str not in (svc.APPROVE_EMOJI, svc.REJECT_EMOJI):
            return False

        with trace_span(
            "reactions.whitelist_resolve",
            attributes={
                "discord.guild_id": str(payload.guild_id),
                "discord.message_id": str(payload.message_id),
                "whitelist.emoji": emoji_str,
            },
        ):
            result = await svc.resolve_reaction(
                server_id=payload.guild_id,
                message_id=payload.message_id,
                moderator_id=payload.user_id,
                emoji=emoji_str,
            )

            if result.outcome is ResolutionOutcome.NOT_APPLICABLE:
                return False

            if result.outcome is ResolutionOutcome.PERMISSION_DENIED:
                logger.info(
                    "Non-mod attempted whitelist %s on message %s in guild %s",
                    emoji_str,
                    payload.message_id,
                    payload.guild_id,
                    extra={"user_id": payload.user_id},
                )
                try:
                    channel = await get_or_fetch_channel(self.bot, payload.channel_id)
                    if channel:
                        msg = await channel.fetch_message(payload.message_id)
                        await msg.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))
                except Exception as e:
                    logger.debug("Could not remove non-mod whitelist reaction: %s", e)
                return True

            if result.outcome is ResolutionOutcome.APPROVED:
                channel = await get_or_fetch_channel(self.bot, result.channel_id)
                if channel:
                    await channel.send(
                        f"✅ **{result.username}** added to whitelist. {result.rcon_response}"
                    )
                author = self.bot.get_user(result.author_id) or await self.bot.fetch_user(
                    result.author_id
                )
                if author:
                    try:
                        await author.send(
                            f"You have been added to the Minecraft whitelist as **{result.username}**."
                        )
                    except discord.Forbidden:
                        logger.debug(
                            "Could not DM whitelist approval to %s (DMs disabled)",
                            result.author_id,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to DM whitelist approval to %s: %s", result.author_id, e
                        )
            elif result.outcome is ResolutionOutcome.APPROVE_FAILED:
                channel = await get_or_fetch_channel(self.bot, result.channel_id)
                if channel:
                    await channel.send(
                        f"❌ Failed to add **{result.username}** to whitelist: {result.error}"
                    )

            try:
                channel = await get_or_fetch_channel(self.bot, result.channel_id)
                if channel:
                    msg = await channel.fetch_message(payload.message_id)
                    await msg.clear_reactions()
                    if result.outcome is ResolutionOutcome.APPROVED:
                        await msg.add_reaction(svc.APPROVE_EMOJI)
            except Exception as e:
                logger.debug("Could not clear whitelist message reactions: %s", e)

        return True

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        role_id = await self._get_reaction_role(
            payload.guild_id, payload.message_id, str(payload.emoji)
        )
        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(role_id) if guild else None

        if not member or not role:
            return

        try:
            with trace_span(
                "reactions.role_revoke",
                attributes={
                    "discord.guild_id": str(payload.guild_id),
                    "discord.role_id": str(role_id),
                },
            ):
                await member.remove_roles(role, reason="Reaction role")
        except discord.HTTPException as e:
            logger.error("Failed to remove role: %s", e)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="role_removal").inc()

    async def _get_reaction_role(self, server_id: int, message_id: int, emoji: str) -> int | None:
        cache_key = f"reaction_role:{server_id}:{message_id}:{emoji}"
        cached = self.bot.cache.get(cache_key) if self.bot.cache else None
        if cached is not None:
            return None if cached == -1 else int(cached)
        try:
            async with self.bot.db_pool.acquire() as conn:
                role_id = await conn.fetchval(
                    "SELECT role_id FROM reaction_roles WHERE server_id = $1 AND message_id = $2 AND emoji = $3 AND is_active = true",
                    server_id,
                    message_id,
                    emoji,
                )
            if self.bot.cache:
                self.bot.cache.set(
                    cache_key, role_id if role_id is not None else -1, ttl=Constants.CACHE_TTL
                )
            return int(role_id) if role_id is not None else None
        except Exception as e:
            logger.error("Error fetching reaction role: %s", e)
            return None


async def setup(bot):
    await bot.add_cog(ReactionHandler(bot))
