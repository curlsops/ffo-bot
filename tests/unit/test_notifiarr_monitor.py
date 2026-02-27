"""Tests for Notifiarr monitor functionality."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.processors.notifiarr_monitor import NotifiarrEvent, NotifiarrMonitor


class TestNotifiarrEvent:
    """Tests for NotifiarrEvent dataclass."""

    def test_notifiarr_event_creation(self):
        """Test creating a NotifiarrEvent."""
        now = datetime.now(timezone.utc)
        event = NotifiarrEvent(
            event_type="grab_failed",
            media_title="Test Movie",
            media_type="movie",
            failure_reason="Connection timeout",
            timestamp=now,
            message_id=123456,
        )

        assert event.event_type == "grab_failed"
        assert event.media_title == "Test Movie"
        assert event.media_type == "movie"
        assert event.failure_reason == "Connection timeout"
        assert event.timestamp == now
        assert event.message_id == 123456


class TestNotifiarrMonitorInit:
    """Tests for NotifiarrMonitor initialization."""

    def test_monitor_initialization(self, mock_db_pool, mock_cache):
        """Test NotifiarrMonitor initialization."""
        mock_metrics = MagicMock()

        monitor = NotifiarrMonitor(mock_db_pool, mock_cache, mock_metrics)

        assert monitor.db_pool == mock_db_pool
        assert monitor.cache == mock_cache
        assert monitor.metrics == mock_metrics

    def test_monitor_without_metrics(self, mock_db_pool, mock_cache):
        """Test NotifiarrMonitor without metrics."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        assert monitor.metrics is None


class TestNotifiarrMonitorDetection:
    """Tests for failure detection methods."""

    def test_detect_failure_grab_failed(self, mock_db_pool, mock_cache):
        """Test detecting grab_failed in content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._detect_failure("Grab Failed for Movie XYZ", [])

        assert result == "grab_failed"

    def test_detect_failure_import_failed(self, mock_db_pool, mock_cache):
        """Test detecting import_failed in content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._detect_failure("Import Failed: Episode not found", [])

        assert result == "import_failed"

    def test_detect_failure_download_failed(self, mock_db_pool, mock_cache):
        """Test detecting download_failed in content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._detect_failure("Download failed - no seeders", [])

        assert result == "download_failed"

    def test_detect_failure_health_check_failed(self, mock_db_pool, mock_cache):
        """Test detecting health_check_failed in content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._detect_failure("Health Check Failed for Sonarr", [])

        assert result == "health_check_failed"

    def test_detect_failure_no_failure(self, mock_db_pool, mock_cache):
        """Test no failure detected."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._detect_failure("Successfully grabbed Movie XYZ", [])

        assert result is None

    def test_detect_failure_in_embed_title(self, mock_db_pool, mock_cache):
        """Test detecting failure in embed title."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_embed = MagicMock()
        mock_embed.title = "Grab Failed"
        mock_embed.description = "Details here"

        result = monitor._detect_failure("", [mock_embed])

        assert result == "grab_failed"

    def test_detect_failure_in_embed_description(self, mock_db_pool, mock_cache):
        """Test detecting failure in embed description."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_embed = MagicMock()
        mock_embed.title = None
        mock_embed.description = "Import failed for this item"

        result = monitor._detect_failure("", [mock_embed])

        assert result == "import_failed"


class TestNotifiarrMonitorExtraction:
    """Tests for data extraction methods."""

    def test_extract_title_from_content(self, mock_db_pool, mock_cache):
        """Test extracting title from message content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._extract_title("Title: The Matrix (1999)", [])

        assert result == "The Matrix (1999)"

    def test_extract_title_from_embed(self, mock_db_pool, mock_cache):
        """Test extracting title from embed."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_embed = MagicMock()
        mock_embed.title = "Inception"
        mock_embed.description = None

        result = monitor._extract_title("", [mock_embed])

        assert result == "Inception"

    def test_extract_title_from_embed_description(self, mock_db_pool, mock_cache):
        """Test extracting title from embed description."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_embed = MagicMock()
        mock_embed.title = None
        mock_embed.description = "Name: Avatar"

        result = monitor._extract_title("", [mock_embed])

        assert result == "Avatar"

    def test_extract_title_not_found(self, mock_db_pool, mock_cache):
        """Test title extraction when not found."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._extract_title("No title here", [])

        assert result is None

    def test_extract_media_type_from_content(self, mock_db_pool, mock_cache):
        """Test extracting media type from content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        assert monitor._extract_media_type("Movie grabbed", []) == "movie"
        assert monitor._extract_media_type("Episode imported", []) == "episode"
        assert monitor._extract_media_type("Series added", []) == "series"
        assert monitor._extract_media_type("Music downloaded", []) == "music"
        assert monitor._extract_media_type("Album released", []) == "album"

    def test_extract_media_type_not_found(self, mock_db_pool, mock_cache):
        """Test media type extraction when not found."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._extract_media_type("Something happened", [])

        assert result is None

    def test_extract_failure_reason_from_embed_field(self, mock_db_pool, mock_cache):
        """Test extracting failure reason from embed field."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_field = MagicMock()
        mock_field.name = "Reason"
        mock_field.value = "  Connection timed out  "

        mock_embed = MagicMock()
        mock_embed.fields = [mock_field]

        result = monitor._extract_failure_reason("", [mock_embed])

        assert result == "Connection timed out"

    def test_extract_failure_reason_truncates_long_content(self, mock_db_pool, mock_cache):
        """Test failure reason truncation for long content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        long_content = "A" * 300

        result = monitor._extract_failure_reason(long_content, [])

        assert len(result) == 200
        assert result.endswith("...")

    def test_extract_failure_reason_returns_content(self, mock_db_pool, mock_cache):
        """Test failure reason returns short content."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        result = monitor._extract_failure_reason("Short error message", [])

        assert result == "Short error message"


class TestNotifiarrMonitorAsync:
    """Tests for async NotifiarrMonitor methods."""

    @pytest.mark.asyncio
    async def test_process_message_wrong_author(self, mock_db_pool, mock_cache):
        """Test process_message ignores non-Notifiarr messages."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_message = MagicMock()
        mock_message.author.id = 12345

        result = await monitor.process_message(mock_message)

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_event(self, mock_db_pool, mock_cache):
        """Test caching an event."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        await monitor._cache_event(123456, "grab_failed", None)

        cached = mock_cache.get("notifiarr_event:123456")
        assert cached == ("grab_failed", None)

    @pytest.mark.asyncio
    async def test_store_failure(self, mock_cache):
        """Test storing failure in database."""
        mock_conn = AsyncMock()

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire

        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        event = NotifiarrEvent(
            event_type="grab_failed",
            media_title="Test Movie",
            media_type="movie",
            failure_reason="Connection timeout",
            timestamp=datetime.now(timezone.utc),
            message_id=123456,
        )

        await monitor._store_failure(999, event)

        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_failure_handles_error(self, mock_cache):
        """Test store_failure handles database errors."""
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("Database error")

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire

        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        event = NotifiarrEvent(
            event_type="grab_failed",
            media_title="Test Movie",
            media_type=None,
            failure_reason=None,
            timestamp=datetime.now(timezone.utc),
            message_id=123456,
        )

        await monitor._store_failure(999, event)

    @pytest.mark.asyncio
    async def test_send_alert(self, mock_cache):
        """Test sending alert to channel."""
        mock_conn = AsyncMock()

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire

        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_channel = AsyncMock()
        event = NotifiarrEvent(
            event_type="grab_failed",
            media_title="Test Movie",
            media_type="movie",
            failure_reason="Connection timeout",
            timestamp=datetime.now(timezone.utc),
            message_id=123456,
        )

        await monitor.send_alert(mock_channel, event)

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args[0][0]
        assert "Notifiarr Failure Alert" in call_args
        assert "Test Movie" in call_args

    @pytest.mark.asyncio
    async def test_send_alert_handles_error(self, mock_db_pool, mock_cache):
        """Test send_alert handles errors gracefully."""
        monitor = NotifiarrMonitor(mock_db_pool, mock_cache)

        mock_channel = AsyncMock()
        mock_channel.send.side_effect = Exception("Send error")

        event = NotifiarrEvent(
            event_type="grab_failed",
            media_title="Test Movie",
            media_type=None,
            failure_reason=None,
            timestamp=datetime.now(timezone.utc),
            message_id=123456,
        )

        await monitor.send_alert(mock_channel, event)
