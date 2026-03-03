import logging

import discord
from discord.ext import commands

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
                    logger.warning("Failed to add reaction %s: %s", emoji, e)
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
            logger.error("Failed to log phrase match: %s", e)

    async def _convert_units(self, message: discord.Message):
        from bot.processors.unit_converter import detect_and_convert

        try:
            converted = detect_and_convert(message.content)
            if converted:
                await message.reply(converted, mention_author=False)
        except Exception as e:
            logger.warning("Unit conversion error: %s", e)

    async def _transcribe_voice_messages(self, message: discord.Message):
        vt = getattr(self.bot, "voice_transcriber", None)
        if not vt:
            return
        for att in message.attachments:
            if not vt.is_voice_attachment(att.filename, att.content_type):
                continue
            try:
                text = await vt.transcribe(att.url, att.filename)
                if text:
                    embed = discord.Embed(
                        description=text[:2000],
                        color=discord.Color.blue(),
                    )
                    embed.set_author(
                        name=f"Voice message from {message.author.display_name}",
                        icon_url=message.author.display_avatar.url,
                    )
                    embed.set_footer(text="Transcribed automatically")
                    await message.reply(embed=embed)
            except Exception as e:
                logger.error("Voice transcription error: %s", e, exc_info=True)

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
