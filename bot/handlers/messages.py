"""Message event handler with full functionality."""

import logging
from typing import Optional

import discord
from discord.ext import commands

from bot.processors.media_downloader import MediaAttachment

logger = logging.getLogger(__name__)


class MessageHandler(commands.Cog):
    """Handle incoming message events."""

    def __init__(self, bot):
        """
        Initialize message handler.

        Args:
            bot: Bot instance
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Process incoming messages.

        Args:
            message: Discord message
        """
        # Ignore bot messages (except Notifiarr)
        if message.author.bot:
            # Check for Notifiarr messages
            if self.bot.notifiarr_monitor and await self._is_notifiarr_channel(message):
                event = await self.bot.notifiarr_monitor.process_message(message)
                if event:
                    # Send alert if failure detected
                    alert_channel_id = await self._get_alert_channel(message.guild.id)
                    if alert_channel_id:
                        alert_channel = message.guild.get_channel(int(alert_channel_id))
                        if alert_channel:
                            await self.bot.notifiarr_monitor.send_alert(alert_channel, event)
            return

        # Ignore DMs
        if not message.guild:
            return

        # Check if bot is shutting down
        if self.bot.is_shutting_down():
            return

        # Log message processing
        logger.debug(f"Processing message {message.id} from {message.author.id}")

        # Update metrics
        if self.bot.metrics:
            self.bot.metrics.messages_processed.labels(server_id=str(message.guild.id)).inc()

        # Check if user has opted out
        if await self._check_user_opt_out(message.guild.id, message.author.id):
            logger.debug(f"User {message.author.id} has opted out of tracking")
            return

        # Process phrase matching
        if message.content and self.bot.phrase_matcher:
            await self._process_phrase_matching(message)

        # Download media if channel is monitored
        if message.attachments and self.bot.media_downloader:
            if await self._is_monitored_channel(message.guild.id, message.channel.id):
                await self._download_media(message)

    async def _process_phrase_matching(self, message: discord.Message):
        """
        Match phrases and add reactions.

        Args:
            message: Discord message
        """
        try:
            matches = await self.bot.phrase_matcher.match_phrases(message.content, message.guild.id)

            for phrase_id, emoji in matches:
                try:
                    await message.add_reaction(emoji)

                    # Update metrics
                    if self.bot.metrics:
                        self.bot.metrics.phrase_matches.labels(
                            server_id=str(message.guild.id), phrase_id=phrase_id
                        ).inc()

                    # Log match to database
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
            logger.error(f"Error processing phrase matching: {e}", exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="phrase_matching").inc()

    async def _download_media(self, message: discord.Message):
        """
        Download media attachments.

        Args:
            message: Discord message
        """
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
            logger.error(f"Error downloading media: {e}", exc_info=True)
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
        """
        Log phrase match to database.

        Args:
            server_id: Discord server ID
            message_id: Discord message ID
            channel_id: Discord channel ID
            user_id: Discord user ID
            phrase_id: Phrase reaction ID
            emoji: Emoji that was added
        """
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO message_metadata
                    (server_id, message_id, channel_id, user_id, phrase_matched, reaction_added)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (message_id) DO NOTHING
                    """,
                    server_id,
                    message_id,
                    channel_id,
                    user_id,
                    phrase_id,
                    emoji,
                )

                # Update match count
                await conn.execute(
                    """
                    UPDATE phrase_reactions
                    SET match_count = match_count + 1,
                        last_matched_at = NOW()
                    WHERE id = $1
                    """,
                    phrase_id,
                )
        except Exception as e:
            logger.error(f"Failed to log phrase match: {e}")

    async def _is_monitored_channel(self, server_id: int, channel_id: int) -> bool:
        """
        Check if channel is monitored for media.

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID

        Returns:
            True if channel is monitored
        """
        try:
            async with self.bot.db_pool.acquire() as conn:
                config = await conn.fetchval(
                    """
                    SELECT config FROM servers WHERE server_id = $1
                    """,
                    server_id,
                )

            if config and "monitored_channels" in config:
                return str(channel_id) in config["monitored_channels"]
            return False
        except Exception as e:
            logger.error(f"Error checking monitored channel: {e}")
            return False

    async def _is_notifiarr_channel(self, message: discord.Message) -> bool:
        """
        Check if message is from Notifiarr in monitored channel.

        Args:
            message: Discord message

        Returns:
            True if message is from Notifiarr
        """
        if message.author.id != self.bot.notifiarr_monitor.NOTIFIARR_BOT_ID:
            return False

        try:
            async with self.bot.db_pool.acquire() as conn:
                config = await conn.fetchval(
                    """
                    SELECT config FROM servers WHERE server_id = $1
                    """,
                    message.guild.id,
                )

            if config and "notifiarr_channels" in config:
                return str(message.channel.id) in config["notifiarr_channels"]
            return False
        except Exception as e:
            logger.error(f"Error checking Notifiarr channel: {e}")
            return False

    async def _get_alert_channel(self, server_id: int) -> Optional[str]:
        """
        Get alert channel ID for server.

        Args:
            server_id: Discord server ID

        Returns:
            Alert channel ID or None
        """
        try:
            async with self.bot.db_pool.acquire() as conn:
                config = await conn.fetchval(
                    """
                    SELECT config FROM servers WHERE server_id = $1
                    """,
                    server_id,
                )

            if config and "alert_channel" in config:
                return config["alert_channel"]
            return None
        except Exception as e:
            logger.error(f"Error getting alert channel: {e}")
            return None

    async def _check_user_opt_out(self, server_id: int, user_id: int) -> bool:
        """
        Check if user has opted out of message tracking.

        Args:
            server_id: Discord server ID
            user_id: Discord user ID

        Returns:
            True if user has opted out
        """
        try:
            async with self.bot.db_pool.acquire() as conn:
                opted_out = await conn.fetchval(
                    """
                    SELECT message_tracking_opt_out FROM user_preferences
                    WHERE server_id = $1 AND user_id = $2
                    """,
                    server_id,
                    user_id,
                )

            return opted_out or False
        except Exception as e:
            logger.error(f"Error checking user opt-out: {e}")
            return False


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(MessageHandler(bot))
