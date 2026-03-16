import asyncio
import logging
from typing import cast

import discord
from discord.ext import commands

from bot.utils.pagination import truncate_for_discord
from bot.utils.server_config import get_servers_config
from bot.utils.user_preferences import OPT_OUT_CACHE_KEY
from config.constants import Constants

logger = logging.getLogger(__name__)


class MessageHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or self.bot.is_shutting_down():
            return

        if self.bot.metrics:
            self.bot.metrics.messages_processed.labels(server_id=str(message.guild.id)).inc()

        if await self._check_user_opt_out(message.guild.id, message.author.id):
            return

        if message.content and self.bot.phrase_matcher:
            await self._process_phrase_matching(message)

        if message.attachments and self.bot.media_downloader:
            if await self._is_monitored_channel(message.guild.id, message.channel.id):
                await self._download_media(message)

        vt = getattr(self.bot, "voice_transcriber", None)
        if message.attachments and vt and vt.enabled:
            await self._transcribe_voice_messages(message)

        if message.content and getattr(self.bot.settings, "feature_conversion", False):
            await self._convert_units(message)

        if getattr(self.bot.settings, "feature_minecraft_whitelist", False):
            await self._process_whitelist_channel(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content or not after.content or after.author.bot:
            return
        if not after.guild or self.bot.is_shutting_down():
            return
        if not self.bot.phrase_matcher:
            return
        if await self._check_user_opt_out(after.guild.id, after.author.id):
            return

        if self.bot.metrics:
            self.bot.metrics.messages_processed.labels(server_id=str(after.guild.id)).inc()

        await self._process_phrase_matching_edit(after)

    async def _process_phrase_matching_edit(self, message: discord.Message):
        try:
            matches = await self.bot.phrase_matcher.match_phrases(message.content, message.guild.id)
            should_have = {emoji for _, emoji in matches}

            try:
                msg = await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return

            current_ours = {str(r.emoji) for r in msg.reactions if r.me}
            to_add = should_have - current_ours
            to_remove = current_ours - should_have

            for emoji in to_remove:
                try:
                    await msg.remove_reaction(emoji, self.bot.user)
                except discord.HTTPException as e:
                    logger.warning("Failed to remove reaction %s: %s", emoji, e)

            logged: list[tuple[int, int, int, int, str, str]] = []
            for emoji in to_add:
                try:
                    await msg.add_reaction(emoji)
                    for phrase_id, matched_emoji in matches:
                        if matched_emoji == emoji:
                            if self.bot.metrics:
                                self.bot.metrics.phrase_matches.labels(
                                    server_id=str(message.guild.id),
                                    phrase_id=phrase_id,
                                ).inc()
                            logged.append(
                                (
                                    message.guild.id,
                                    message.id,
                                    message.channel.id,
                                    message.author.id,
                                    phrase_id,
                                    emoji,
                                )
                            )
                except discord.HTTPException as e:
                    logger.warning("Failed to add reaction %s: %s", emoji, e)
            if logged:
                await self._log_phrase_matches_batch(logged)
        except Exception as e:
            logger.error("Phrase matching edit error: %s", e, exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="phrase_matching").inc()

    async def _process_whitelist_channel(self, message: discord.Message):
        from bot.commands.whitelist import WHITELIST_APPROVE_EMOJI, WHITELIST_REJECT_EMOJI
        from bot.services.mojang import get_profile
        from bot.utils.whitelist_channel import get_whitelist_channel_id

        if not message.guild or not message.content:
            return
        channel_id = await get_whitelist_channel_id(
            self.bot.db_pool, message.guild.id, cache=self.bot.cache
        )
        if channel_id != message.channel.id:
            return

        content = message.content.strip()
        if not content or " " in content:
            return

        if not (3 <= len(content) <= 16) or not content.replace("_", "").isalnum():
            return

        username = content
        profile = await get_profile(username)
        if profile:
            uuid_val, _ = profile
            try:
                await message.add_reaction(WHITELIST_APPROVE_EMOJI)
                await message.add_reaction(WHITELIST_REJECT_EMOJI)
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO whitelist_pending (server_id, message_id, channel_id, username, author_id, minecraft_uuid)
                        VALUES ($1, $2, $3, $4, $5, $6::uuid)
                        ON CONFLICT (server_id, message_id) DO NOTHING
                        """,
                        message.guild.id,
                        message.id,
                        message.channel.id,
                        username,
                        message.author.id,
                        uuid_val,
                    )
            except discord.HTTPException as e:
                logger.warning("Failed to add whitelist reactions: %s", e)
            except Exception as e:
                logger.error("Whitelist pending insert error: %s", e, exc_info=True)
        else:
            await message.reply(
                f"{message.author.mention} Your Minecraft username does not exist. Please try again."
            )

    async def _process_phrase_matching(self, message: discord.Message):
        try:
            matches = await self.bot.phrase_matcher.match_phrases(message.content, message.guild.id)
            logged: list[tuple[int, int, int, int, str, str]] = []
            for phrase_id, emoji in matches:
                try:
                    await message.add_reaction(emoji)
                    if self.bot.metrics:
                        self.bot.metrics.phrase_matches.labels(
                            server_id=str(message.guild.id), phrase_id=phrase_id
                        ).inc()
                    logged.append(
                        (
                            message.guild.id,
                            message.id,
                            message.channel.id,
                            message.author.id,
                            phrase_id,
                            emoji,
                        )
                    )
                except discord.HTTPException as e:
                    logger.warning("Failed to add reaction %s: %s", emoji, e)
            if logged:
                await self._log_phrase_matches_batch(logged)
        except Exception as e:
            logger.error("Phrase matching error: %s", e, exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="phrase_matching").inc()

    async def _download_media(self, message: discord.Message):
        from bot.processors.media_downloader import MediaAttachment

        try:
            attachments = [
                MediaAttachment(
                    url=att.url,
                    filename=att.filename,
                    content_type=att.content_type or "application/octet-stream",
                    size_bytes=att.size,
                )
                for att in message.attachments
            ]
            await self.bot.media_downloader.download_media(
                message_id=message.id,
                channel_id=message.channel.id,
                server_id=message.guild.id,
                uploader_id=message.author.id,
                attachments=attachments,
            )
        except Exception as e:
            logger.error("Media download error: %s", e, exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="media_download").inc()

    async def _log_phrase_matches_batch(
        self,
        rows: list[tuple[int, int, int, int, str, str]],
    ):
        if not rows:
            return
        try:
            seen_msg: dict[int, tuple[int, int, int, int, str, str]] = {}
            for server_id, message_id, channel_id, user_id, phrase_id, emoji in rows:
                if message_id not in seen_msg:
                    seen_msg[message_id] = (
                        server_id,
                        message_id,
                        channel_id,
                        user_id,
                        phrase_id,
                        emoji,
                    )
            phrase_ids = [r[4] for r in rows]
            async with self.bot.db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO message_metadata (server_id, message_id, channel_id, user_id, phrase_matched, reaction_added)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (message_id) DO NOTHING
                    """,
                    list(seen_msg.values()),
                )
                await conn.execute(
                    """
                    UPDATE phrase_reactions pr
                    SET match_count = match_count + sub.cnt, last_matched_at = NOW()
                    FROM (
                        SELECT id, COUNT(*)::int AS cnt
                        FROM unnest($1::text[]) AS id
                        GROUP BY id
                    ) sub
                    WHERE pr.id = sub.id
                    """,
                    phrase_ids,
                )
        except Exception as e:
            logger.error("Failed to log phrase matches: %s", e)

    async def _convert_units(self, message: discord.Message):
        from bot.processors.unit_converter import detect_and_convert

        try:
            converted = detect_and_convert(message.content)
            if converted:
                embed = discord.Embed(
                    description=converted,
                    color=discord.Color.blue(),
                )
                embed.set_footer(text="Converted from imperial to SI")
                await message.reply(embed=embed, mention_author=False)
        except Exception as e:
            logger.warning("Unit conversion error: %s", e)

    async def _transcribe_voice_messages(self, message: discord.Message):
        vt = getattr(self.bot, "voice_transcriber", None)
        if not vt:
            return
        atts = [
            att
            for att in message.attachments
            if vt.is_voice_attachment(att.filename, att.content_type)
        ]
        if not atts:
            return
        results = await asyncio.gather(
            *[vt.transcribe(att.url, att.filename) for att in atts],
            return_exceptions=True,
        )
        for att, result in zip(atts, results):
            if isinstance(result, Exception):
                logger.error("Voice transcription error: %s", result, exc_info=True)
            elif result:
                embed = discord.Embed(
                    description=truncate_for_discord(cast(str, result)),
                    color=discord.Color.blue(),
                )
                embed.set_author(
                    name=f"Voice message from {message.author.display_name}",
                    icon_url=message.author.display_avatar.url,
                )
                embed.set_footer(text="Transcribed automatically")
                await message.reply(embed=embed)

    async def _is_monitored_channel(self, server_id: int, channel_id: int) -> bool:
        cfg = await get_servers_config(self.bot.db_pool, server_id, self.bot.cache)
        return bool(cfg.get("monitored_channels") and str(channel_id) in cfg["monitored_channels"])

    async def _check_user_opt_out(self, server_id: int, user_id: int) -> bool:
        cache_key = OPT_OUT_CACHE_KEY.format(server_id=server_id, user_id=user_id)
        if self.bot.cache:
            cached = self.bot.cache.get(cache_key)
            if cached is not None:
                return bool(cached)
        try:
            async with self.bot.db_pool.acquire() as conn:
                val = await conn.fetchval(
                    "SELECT message_tracking_opt_out FROM user_preferences WHERE server_id = $1 AND user_id = $2",
                    server_id,
                    user_id,
                )
            result = bool(val)
            if self.bot.cache:
                self.bot.cache.set(cache_key, result, ttl=Constants.CACHE_TTL)
            return result
        except Exception:
            return False


async def setup(bot):
    await bot.add_cog(MessageHandler(bot))
