"""Main Discord bot client with lifecycle management."""

import asyncio
import logging
from typing import Optional

import discord
from aiohttp import web
from discord.ext import commands

from bot.auth.permissions import PermissionChecker
from bot.cache.memory import InMemoryCache
from bot.processors.media_downloader import MediaDownloader
from bot.processors.notifiarr_monitor import NotifiarrMonitor
from bot.processors.phrase_matcher import PhraseMatcher
from bot.utils.metrics import BotMetrics
from bot.utils.rate_limiter import RateLimiter
from config.settings import Settings
from database.connection import DatabasePool

logger = logging.getLogger(__name__)


class FFOBot(commands.Bot):
    """
    Main bot client with lifecycle management.

    Handles:
    - Discord connection and event processing
    - Database connection pooling
    - In-memory caching
    - Health checks and metrics
    - Graceful shutdown
    """

    def __init__(self, settings: Settings):
        """
        Initialize bot client.

        Args:
            settings: Application settings
        """
        # Configure intents
        intents = discord.Intents.default()
        intents.message_content = True  # Required for message processing
        intents.guilds = True
        intents.members = True  # For permission checks
        intents.reactions = True  # For reaction roles

        super().__init__(
            command_prefix="!",  # Prefix for legacy commands (not used)
            intents=intents,
            help_command=None,  # Disable default help command
        )

        self.settings = settings
        self.db_pool: Optional[DatabasePool] = None
        self.cache: Optional[InMemoryCache] = None
        self.metrics: Optional[BotMetrics] = None
        self.phrase_matcher: Optional[PhraseMatcher] = None
        self.media_downloader: Optional[MediaDownloader] = None
        self.notifiarr_monitor: Optional[NotifiarrMonitor] = None
        self.permission_checker: Optional[PermissionChecker] = None
        self.rate_limiter: Optional[RateLimiter] = None
        self._shutdown_event = asyncio.Event()
        self._health_server: Optional[web.AppRunner] = None

    async def setup_hook(self):
        """Initialize resources before connecting to Discord."""
        logger.info("Initializing bot resources...")

        # Initialize database connection pool
        self.db_pool = await DatabasePool.create(
            self.settings.database_url,
            min_size=self.settings.db_pool_min_size,
            max_size=self.settings.db_pool_max_size,
        )
        logger.info(
            f"Database connection pool established "
            f"(min: {self.settings.db_pool_min_size}, max: {self.settings.db_pool_max_size})"
        )

        # Initialize in-memory cache
        self.cache = InMemoryCache(
            max_size=self.settings.cache_max_size, default_ttl=self.settings.cache_default_ttl
        )
        logger.info(f"In-memory cache initialized (max_size: {self.settings.cache_max_size})")

        # Initialize metrics
        self.metrics = BotMetrics()
        logger.info("Metrics initialized")

        # Initialize phrase matcher
        self.phrase_matcher = PhraseMatcher(self.db_pool, self.cache)
        logger.info("Phrase matcher initialized")

        # Initialize media downloader
        if self.settings.feature_media_download:
            self.media_downloader = MediaDownloader(
                self.db_pool, self.settings.media_storage_path, self.metrics
            )
            await self.media_downloader.initialize()
            logger.info("Media downloader initialized")

        # Initialize Notifiarr monitor
        if self.settings.feature_notifiarr_monitoring:
            self.notifiarr_monitor = NotifiarrMonitor(self.db_pool, self.cache, self.metrics)
            logger.info("Notifiarr monitor initialized")

        # Initialize permission checker
        self.permission_checker = PermissionChecker(self.db_pool, self.cache)
        logger.info("Permission checker initialized")

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            user_capacity=self.settings.rate_limit_user_capacity,
            server_capacity=self.settings.rate_limit_server_capacity,
        )
        logger.info("Rate limiter initialized")

        # Start health check server
        await self._start_health_server()

        # Load extensions (commands and handlers)
        await self._load_extensions()

        # Sync slash commands with Discord
        logger.info("Syncing slash commands with Discord...")
        await self.tree.sync()
        logger.info("Slash commands synced")

    async def _load_extensions(self):
        """Load bot extensions (commands and event handlers)."""
        extensions = [
            "bot.handlers.messages",
            "bot.handlers.reactions",
            "bot.commands.admin",
            "bot.commands.permissions",
            "bot.commands.reactbot",
            "bot.commands.privacy",
        ]

        for extension in extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}", exc_info=True)

    async def _start_health_server(self):
        """Start HTTP server for health checks and metrics."""
        from bot.utils.health import HealthCheckServer

        health_server = HealthCheckServer(self, port=self.settings.health_check_port)
        await health_server.start()
        self._health_server = health_server.runner

        logger.info(f"Health check server started on port {self.settings.health_check_port}")

    async def on_ready(self):
        """Called when bot successfully connects to Discord."""
        logger.info("=" * 60)
        logger.info(f"Bot connected as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} servers")
        logger.info("=" * 60)

        # Register servers in database
        for guild in self.guilds:
            await self._register_server(guild)

        # Update metrics
        if self.metrics:
            self.metrics.set_guild_count(len(self.guilds))
            self.metrics.set_connection_status(1)

        logger.info("Bot is ready!")

    async def _register_server(self, guild: discord.Guild):
        """
        Ensure server exists in database.

        Args:
            guild: Discord guild to register
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO servers (server_id, server_name)
                    VALUES ($1, $2)
                    ON CONFLICT (server_id) DO UPDATE
                    SET server_name = EXCLUDED.server_name,
                        updated_at = NOW()
                    """,
                    guild.id,
                    guild.name,
                )
                logger.debug(f"Registered server: {guild.name} ({guild.id})")
        except Exception as e:
            logger.error(f"Failed to register server {guild.id}: {e}", exc_info=True)

    async def on_guild_join(self, guild: discord.Guild):
        """Called when bot joins a new server."""
        logger.info(f"Joined new server: {guild.name} ({guild.id})")
        await self._register_server(guild)

        if self.metrics:
            self.metrics.set_guild_count(len(self.guilds))

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when bot is removed from a server."""
        logger.info(f"Removed from server: {guild.name} ({guild.id})")

        if self.metrics:
            self.metrics.set_guild_count(len(self.guilds))

    async def close(self):
        """Graceful shutdown with resource cleanup."""
        logger.info("Starting graceful shutdown...")

        # Set shutdown flag
        self._shutdown_event.set()

        # Update metrics
        if self.metrics:
            self.metrics.set_connection_status(0)

        # Wait for in-flight messages (up to configured timeout)
        try:
            await asyncio.wait_for(
                self._drain_message_queue(), timeout=self.settings.shutdown_timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Message drain timeout ({self.settings.shutdown_timeout_seconds}s) reached"
            )

        # Stop health server
        if self._health_server:
            await self._health_server.cleanup()
            logger.info("Health check server stopped")

        # Close media downloader
        if self.media_downloader:
            await self.media_downloader.close()
            logger.info("Media downloader closed")

        # Close database connections
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Database connections closed")

        # Clear cache
        if self.cache:
            self.cache.clear()
            logger.info("Cache cleared")

        # Close Discord connection
        await super().close()
        logger.info("Discord connection closed")

    async def _drain_message_queue(self):
        """Wait for pending messages to process."""
        # Get all pending tasks related to message processing
        pending_tasks = [
            task
            for task in asyncio.all_tasks()
            if not task.done() and "on_message" in str(task.get_coro())
        ]

        if pending_tasks:
            logger.info(f"Waiting for {len(pending_tasks)} pending message tasks")
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            logger.info("All pending message tasks completed")

    def is_shutting_down(self) -> bool:
        """Check if bot is shutting down."""
        return self._shutdown_event.is_set()
