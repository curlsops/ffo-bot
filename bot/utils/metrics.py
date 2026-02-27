"""Prometheus metrics for bot monitoring."""

import logging

from prometheus_client import Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger(__name__)


class BotMetrics:
    """Prometheus metrics collector for bot operations."""

    def __init__(self):
        """Initialize all metrics."""
        # Messages
        self.messages_processed = Counter(
            "bot_messages_processed_total", "Total messages processed", ["server_id"]
        )

        # Phrase matching
        self.phrase_matches = Counter(
            "bot_phrase_matches_total", "Total phrase matches", ["server_id", "phrase_id"]
        )

        # Commands
        self.commands_executed = Counter(
            "bot_commands_executed_total",
            "Total commands executed",
            ["command_name", "server_id", "status"],
        )

        self.command_duration = Histogram(
            "bot_command_duration_seconds", "Command execution duration", ["command_name"]
        )

        # Media downloads
        self.media_downloads = Counter(
            "bot_media_downloads_total",
            "Total media downloads",
            ["server_id", "file_type", "status"],
        )

        self.media_download_duration = Histogram(
            "bot_media_download_duration_seconds", "Media download duration", ["file_type"]
        )

        # Database
        self.db_query_duration = Histogram(
            "bot_db_query_duration_seconds", "Database query duration", ["query_type"]
        )

        self.db_connection_errors = Counter(
            "bot_db_connection_errors_total", "Database connection errors"
        )

        # Connection status
        self.active_connections = Gauge(
            "bot_active_connections", "Number of active Discord connections"
        )

        self.guild_count = Gauge("bot_guild_count", "Number of guilds bot is connected to")

        # Cache
        self.cache_size = Gauge("bot_cache_size", "Current cache size")

        self.cache_hits = Counter("bot_cache_hits_total", "Cache hits")

        self.cache_misses = Counter("bot_cache_misses_total", "Cache misses")

        # Notifiarr
        self.notifiarr_failures = Counter(
            "bot_notifiarr_failures_total",
            "Notifiarr failures detected",
            ["server_id", "failure_type"],
        )

        # Errors
        self.errors_total = Counter("bot_errors_total", "Total errors", ["error_type"])

        logger.info("Metrics initialized")

    def set_connection_status(self, status: int):
        """Set connection status (0=disconnected, 1=connected)."""
        self.active_connections.set(status)

    def set_guild_count(self, count: int):
        """Set guild count."""
        self.guild_count.set(count)

    def set_cache_size(self, size: int):
        """Set cache size."""
        self.cache_size.set(size)


def generate_metrics_response():
    """
    Generate Prometheus metrics text response.

    Returns:
        Metrics in Prometheus text format
    """
    return generate_latest()
