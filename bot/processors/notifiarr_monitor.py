"""Notifiarr message parser and alerting."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class NotifiarrEvent:
    """Notifiarr event data."""

    event_type: str
    media_title: str
    media_type: Optional[str]
    failure_reason: Optional[str]
    timestamp: datetime
    message_id: int


class NotifiarrMonitor:
    """Parse Notifiarr messages and detect failures."""

    # Known Notifiarr bot user ID (replace with actual ID)
    NOTIFIARR_BOT_ID = 0  # TODO: Set actual Notifiarr bot ID

    # Event cache TTL (5 minutes)
    EVENT_CACHE_TTL = 300

    # Failure patterns to detect
    FAILURE_PATTERNS = {
        "grab_failed": re.compile(r"grab\s+failed", re.IGNORECASE),
        "import_failed": re.compile(r"import\s+failed", re.IGNORECASE),
        "download_failed": re.compile(r"download\s+failed", re.IGNORECASE),
        "health_check_failed": re.compile(r"health\s+check\s+failed", re.IGNORECASE),
    }

    # Media title extraction pattern
    TITLE_PATTERN = re.compile(r"(?:title|name):\s*([^\n]+)", re.IGNORECASE)

    # Media type extraction
    TYPE_PATTERN = re.compile(r"(?:movie|episode|series|music|album)", re.IGNORECASE)

    def __init__(self, db_pool, cache, metrics=None):
        """
        Initialize Notifiarr monitor.

        Args:
            db_pool: Database connection pool
            cache: In-memory cache
            metrics: Metrics collector (optional)
        """
        self.db_pool = db_pool
        self.cache = cache
        self.metrics = metrics

    async def process_message(self, message) -> Optional[NotifiarrEvent]:
        """
        Process Notifiarr message and detect failures.

        Args:
            message: Discord message

        Returns:
            NotifiarrEvent if failure detected, None otherwise
        """
        # Check if message is from Notifiarr
        if message.author.id != self.NOTIFIARR_BOT_ID:
            return None

        content = message.content
        embeds = message.embeds

        # Parse message for failure indicators
        failure_type = self._detect_failure(content, embeds)

        if not failure_type:
            # Cache non-failure event
            await self._cache_event(message.id, "success", None)
            return None

        # Extract media information
        media_title = self._extract_title(content, embeds)
        media_type = self._extract_media_type(content, embeds)
        failure_reason = self._extract_failure_reason(content, embeds)

        event = NotifiarrEvent(
            event_type=failure_type,
            media_title=media_title or "Unknown",
            media_type=media_type,
            failure_reason=failure_reason,
            timestamp=message.created_at,
            message_id=message.id,
        )

        # Store failure in database
        await self._store_failure(message.guild.id, event)

        # Cache event
        await self._cache_event(message.id, failure_type, event)

        # Update metrics
        if self.metrics:
            self.metrics.notifiarr_failures.labels(
                server_id=str(message.guild.id), failure_type=failure_type
            ).inc()

        logger.info(f"Detected Notifiarr failure: {failure_type} - {media_title}")

        return event

    def _detect_failure(self, content: str, embeds: list) -> Optional[str]:
        """
        Detect failure type from message content and embeds.

        Args:
            content: Message text content
            embeds: Message embeds

        Returns:
            Failure type or None
        """
        # Check message content
        for failure_type, pattern in self.FAILURE_PATTERNS.items():
            if pattern.search(content):
                return failure_type

        # Check embeds
        for embed in embeds:
            # Check embed title
            if embed.title and any(
                pattern.search(embed.title) for pattern in self.FAILURE_PATTERNS.values()
            ):
                for failure_type, pattern in self.FAILURE_PATTERNS.items():
                    if pattern.search(embed.title):
                        return failure_type

            # Check embed description
            if embed.description and any(
                pattern.search(embed.description) for pattern in self.FAILURE_PATTERNS.values()
            ):
                for failure_type, pattern in self.FAILURE_PATTERNS.items():
                    if pattern.search(embed.description):
                        return failure_type

        return None

    def _extract_title(self, content: str, embeds: list) -> Optional[str]:
        """Extract media title from message."""
        # Try content first
        match = self.TITLE_PATTERN.search(content)
        if match:
            return match.group(1).strip()

        # Try embeds
        for embed in embeds:
            if embed.title:
                return embed.title.strip()
            if embed.description:
                match = self.TITLE_PATTERN.search(embed.description)
                if match:
                    return match.group(1).strip()

        return None

    def _extract_media_type(self, content: str, embeds: list) -> Optional[str]:
        """Extract media type from message."""
        # Check content
        match = self.TYPE_PATTERN.search(content)
        if match:
            return match.group(0).lower()

        # Check embeds
        for embed in embeds:
            if embed.title:
                match = self.TYPE_PATTERN.search(embed.title)
                if match:
                    return match.group(0).lower()
            if embed.description:
                match = self.TYPE_PATTERN.search(embed.description)
                if match:
                    return match.group(0).lower()

        return None

    def _extract_failure_reason(self, content: str, embeds: list) -> Optional[str]:
        """Extract failure reason from message."""
        # Look for reason in embeds
        for embed in embeds:
            for field in embed.fields:
                if "reason" in field.name.lower():
                    return field.value.strip()

        # If no specific reason found, return part of content
        if len(content) > 200:
            return content[:197] + "..."
        return content if content else None

    async def _cache_event(self, message_id: int, event_type: str, event: Optional[NotifiarrEvent]):
        """
        Cache event for deduplication.

        Args:
            message_id: Discord message ID
            event_type: Event type
            event: Event data (or None for success)
        """
        cache_key = f"notifiarr_event:{message_id}"
        self.cache.set(cache_key, (event_type, event), ttl=self.EVENT_CACHE_TTL)

    async def _store_failure(self, server_id: int, event: NotifiarrEvent):
        """
        Store failure in database.

        Args:
            server_id: Discord server ID
            event: Notifiarr event
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO notifiarr_failures (
                        server_id, failure_type, media_title, media_type,
                        failure_reason, notifiarr_message_id
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    server_id,
                    event.event_type,
                    event.media_title,
                    event.media_type,
                    event.failure_reason,
                    event.message_id,
                )
        except Exception as e:
            logger.error(f"Failed to store Notifiarr failure: {e}", exc_info=True)

    async def send_alert(self, channel, event: NotifiarrEvent):
        """
        Send failure alert to channel.

        Args:
            channel: Discord channel
            event: Notifiarr event
        """
        try:
            alert_message = (
                f"🚨 **Notifiarr Failure Alert**\n\n"
                f"**Type:** {event.event_type.replace('_', ' ').title()}\n"
                f"**Media:** {event.media_title}"
            )

            if event.media_type:
                alert_message += f"\n**Type:** {event.media_type.title()}"

            if event.failure_reason:
                alert_message += f"\n**Reason:** {event.failure_reason}"

            alert_message += f"\n**Time:** {event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"

            await channel.send(alert_message)

            # Update database
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE notifiarr_failures
                    SET alert_sent = true, alert_sent_at = NOW()
                    WHERE notifiarr_message_id = $1
                    """,
                    event.message_id,
                )

        except Exception as e:
            logger.error(f"Failed to send Notifiarr alert: {e}", exc_info=True)
