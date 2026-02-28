"""Prometheus metrics for bot monitoring."""

import logging

from prometheus_client import Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger(__name__)


class BotMetrics:
    def __init__(self):
        self.messages_processed = Counter(
            "bot_messages_processed_total", "Total messages processed", ["server_id"]
        )
        self.phrase_matches = Counter(
            "bot_phrase_matches_total", "Total phrase matches", ["server_id", "phrase_id"]
        )
        self.commands_executed = Counter(
            "bot_commands_executed_total",
            "Total commands executed",
            ["command_name", "server_id", "status"],
        )
        self.command_duration = Histogram(
            "bot_command_duration_seconds", "Command execution duration", ["command_name"]
        )
        self.media_downloads = Counter(
            "bot_media_downloads_total",
            "Total media downloads",
            ["server_id", "file_type", "status"],
        )
        self.media_download_duration = Histogram(
            "bot_media_download_duration_seconds", "Media download duration", ["file_type"]
        )
        self.db_query_duration = Histogram(
            "bot_db_query_duration_seconds", "Database query duration", ["query_type"]
        )
        self.db_connection_errors = Counter(
            "bot_db_connection_errors_total", "Database connection errors"
        )
        self.active_connections = Gauge(
            "bot_active_connections", "Number of active Discord connections"
        )
        self.guild_count = Gauge("bot_guild_count", "Number of guilds bot is connected to")
        self.cache_size = Gauge("bot_cache_size", "Current cache size")
        self.cache_hits = Counter("bot_cache_hits_total", "Cache hits")
        self.cache_misses = Counter("bot_cache_misses_total", "Cache misses")
        self.errors_total = Counter("bot_errors_total", "Total errors", ["error_type"])

    def set_connection_status(self, status: int):
        self.active_connections.set(status)

    def set_guild_count(self, count: int):
        self.guild_count.set(count)

    def set_cache_size(self, size: int):
        self.cache_size.set(size)


def generate_metrics_response():
    return generate_latest()
