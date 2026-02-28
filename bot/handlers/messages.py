"""Message event handler."""

import logging

import discord
from discord.ext import commands

from bot.processors.media_downloader import MediaAttachment

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

    async def _process_phrase_matching(self, message: discord.Message):
        try:
            matches = await self.bot.phrase_matcher.match_phrases(message.content, message.guild.id)
            for phrase_id, emoji in matches:
                try:
                    await message.add_reaction(emoji)
                    if self.bot.metrics:
                        self.bot.metrics.phrase_matches.labels(
                            server_id=str(message.guild.id), phrase_id=phrase_id
                        ).inc()
                    await self._log_phrase_match(
                        message.guild.id,
                        message.id,
                        message.channel.id,
                        message.author.id,
                        phrase_id,
                        emoji,
                    )
                except discord.HTTPException as e:
                    logger.warning(f"Failed to add reaction {emoji}: {e}")
        except Exception as e:
            logger.error(f"Phrase matching error: {e}", exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="phrase_matching").inc()

    async def _download_media(self, message: discord.Message):
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
            logger.error(f"Media download error: {e}", exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="media_download").inc()

    async def _log_phrase_match(
        self,
        server_id: int,
        message_id: int,
        channel_id: int,
        user_id: int,
        phrase_id: str,
        emoji: str,
    ):
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO message_metadata (server_id, message_id, channel_id, user_id, phrase_matched, reaction_added) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (message_id) DO NOTHING",
                    server_id,
                    message_id,
                    channel_id,
                    user_id,
                    phrase_id,
                    emoji,
                )
                await conn.execute(
                    "UPDATE phrase_reactions SET match_count = match_count + 1, last_matched_at = NOW() WHERE id = $1",
                    phrase_id,
                )
        except Exception as e:
            logger.error(f"Failed to log phrase match: {e}")

    async def _is_monitored_channel(self, server_id: int, channel_id: int) -> bool:
        try:
            async with self.bot.db_pool.acquire() as conn:
                config = await conn.fetchval(
                    "SELECT config FROM servers WHERE server_id = $1", server_id
                )
            return (
                config
                and "monitored_channels" in config
                and str(channel_id) in config["monitored_channels"]
            )
        except Exception:
            return False

    async def _check_user_opt_out(self, server_id: int, user_id: int) -> bool:
        try:
            async with self.bot.db_pool.acquire() as conn:
                return (
                    await conn.fetchval(
                        "SELECT message_tracking_opt_out FROM user_preferences WHERE server_id = $1 AND user_id = $2",
                        server_id,
                        user_id,
                    )
                    or False
                )
        except Exception:
            return False


async def setup(bot):
    await bot.add_cog(MessageHandler(bot))
