from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import TYPE_CHECKING, Optional

import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionChecker
from bot.cache.memory import InMemoryCache
from bot.processors.phrase_matcher import PhraseMatcher
from bot.utils.health import HealthCheckServer
from bot.utils.metrics import BotMetrics
from bot.utils.notifier import AdminNotifier
from bot.utils.rate_limiter import RateLimiter
from config.settings import Settings
from database.connection import DatabasePool

if TYPE_CHECKING:
    from bot.processors.media_downloader import MediaDownloader
    from bot.processors.voice_transcriber import VoiceTranscriber
    from bot.services.minecraft_rcon import MinecraftRCONClient

logger = logging.getLogger(__name__)


class MetricsCommandTree(app_commands.CommandTree):
    async def _call(self, interaction: discord.Interaction) -> None:
        start = time.perf_counter()
        command_name = "unknown"
        server_id = str(interaction.guild_id) if interaction.guild_id else "0"
        try:
            data = interaction.data or {}
            if data.get("type", 1) == 1:
                command, _ = self._get_app_command_options(data)
                command_name = command.qualified_name if command else "unknown"
            else:
                command_name = data.get("name", "unknown")
            await super()._call(interaction)
        finally:
            if self.client.metrics:
                status = "error" if getattr(interaction, "command_failed", False) else "success"
                self.client.metrics.commands_executed.labels(
                    command_name=command_name,
                    server_id=server_id,
                    status=status,
                ).inc()
                self.client.metrics.command_duration.labels(command_name=command_name).observe(
                    time.perf_counter() - start
                )


class FFOBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.reactions = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            tree_cls=MetricsCommandTree,
        )

        self.settings = settings
        self.db_pool: Optional[DatabasePool] = None
        self.cache: Optional[InMemoryCache] = None
        self.metrics: Optional[BotMetrics] = None
        self.phrase_matcher: Optional[PhraseMatcher] = None
        self.media_downloader: Optional[MediaDownloader] = None
        self.voice_transcriber: Optional[VoiceTranscriber] = None
        self.permission_checker: Optional[PermissionChecker] = None
        self.rate_limiter: Optional[RateLimiter] = None
        self.notifier: Optional[AdminNotifier] = None
        self.minecraft_rcon: Optional[MinecraftRCONClient] = None
        self._shutdown_event = asyncio.Event()
        self._health_server: Optional[web.AppRunner] = None

    async def setup_hook(self):
        logger.info("Initializing...")
        self.metrics = BotMetrics()
        self.db_pool = await DatabasePool.create(
            self.settings.database_url,
            min_size=self.settings.db_pool_min_size,
            max_size=self.settings.db_pool_max_size,
            connection_timeout=self.settings.db_connection_timeout,
            acquire_timeout=self.settings.db_acquire_timeout,
            metrics=self.metrics,
        )
        self.cache = InMemoryCache(
            max_size=self.settings.cache_max_size, default_ttl=self.settings.cache_default_ttl
        )

        self.phrase_matcher = PhraseMatcher(self.db_pool, self.cache)

        if self.settings.feature_media_download:
            from bot.processors.media_downloader import MediaDownloader

            self.media_downloader = MediaDownloader(
                self.db_pool, self.settings.media_storage_path, self.metrics
            )
            await self.media_downloader.initialize()

        if self.settings.feature_voice_transcription and self.settings.openai_api_key:
            from bot.processors.voice_transcriber import VoiceTranscriber

            self.voice_transcriber = VoiceTranscriber(api_key=self.settings.openai_api_key)

        self.permission_checker = PermissionChecker(self.db_pool, self.cache, self)
        self.rate_limiter = RateLimiter(
            user_capacity=self.settings.rate_limit_user_capacity,
            server_capacity=self.settings.rate_limit_server_capacity,
        )
        self.notifier = AdminNotifier(self)
        if self.settings.feature_minecraft_whitelist:
            from bot.services.minecraft_rcon import MinecraftRCONClient

            self.minecraft_rcon = MinecraftRCONClient(self.settings)
        self.tree.on_error = self._on_app_command_error

        await self._start_health_server()
        await self._load_extensions()
        await self._register_persistent_views()
        logger.info("Ready")

    async def _load_extensions(self):
        extensions = [
            "bot.handlers.messages",
            "bot.handlers.reactions",
            "bot.commands.admin",
            "bot.commands.permissions",
            "bot.commands.reactbot",
            "bot.commands.privacy",
            "bot.commands.giveaway",
            "bot.commands.polls",
            "bot.commands.reaction_roles",
            "bot.tasks.giveaway_manager",
            "bot.tasks.status_rotator",
        ]
        if self.settings.feature_quotebook:
            extensions.append("bot.commands.quotebook")
        if self.settings.feature_conversion:
            extensions.append("bot.commands.convert")
        if self.settings.feature_minecraft_whitelist:
            extensions.append("bot.commands.whitelist")
        if self.settings.feature_faq:
            extensions.append("bot.commands.faq")

        for extension in extensions:
            try:
                await self.load_extension(extension)
            except Exception as e:
                logger.error("Failed to load extension %s: %s", extension, e, exc_info=True)

    async def _start_health_server(self):
        health_server = HealthCheckServer(self, port=self.settings.health_check_port)
        await health_server.start()
        self._health_server = health_server.runner

    async def _register_persistent_views(self):
        if self.settings.feature_giveaways:
            from bot.commands.giveaway import GiveawayView
            from bot.tasks.giveaway_manager import CloseGiveawayThreadView

            self.add_view(CloseGiveawayThreadView(host_id=0))

            async with self.db_pool.acquire() as conn:
                active = await conn.fetch(
                    "SELECT id, message_id FROM giveaways WHERE is_active = true AND message_id IS NOT NULL"
                )
                for row in active:
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = $1", row["id"]
                    )
                    self.add_view(
                        GiveawayView(row["id"], self, entry_count=count or 0),
                        message_id=row["message_id"],
                    )

    async def on_ready(self):
        logger.info(
            "Connected as %s (ID: %s) to %d servers", self.user, self.user.id, len(self.guilds)
        )

        for guild in self.guilds:
            await self._register_server(guild)

        await self._connection.http.bulk_upsert_global_commands(self.application_id, [])
        for guild in self.guilds:
            await self._connection.http.bulk_upsert_guild_commands(
                self.application_id, guild.id, []
            )
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        if self.guilds:
            logger.info("Synced slash commands to %d guild(s)", len(self.guilds))
        else:
            await self.tree.sync()

        if self.metrics:
            self.metrics.set_guild_count(len(self.guilds))
            self.metrics.set_connection_status(1)

    async def _register_server(self, guild: discord.Guild):
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
        except Exception as e:
            logger.error("Failed to register server %s: %s", guild.id, e, exc_info=True)

    async def on_guild_join(self, guild: discord.Guild):
        logger.info("Joined server: %s (%s)", guild.name, guild.id)
        await self._register_server(guild)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        if self.metrics:
            self.metrics.set_guild_count(len(self.guilds))

    async def on_guild_remove(self, guild: discord.Guild):
        logger.info("Left server: %s (%s)", guild.name, guild.id)
        if self.metrics:
            self.metrics.set_guild_count(len(self.guilds))

    async def close(self):
        logger.info("Shutting down...")
        self._shutdown_event.set()

        if self.metrics:
            self.metrics.set_connection_status(0)

        try:
            await asyncio.wait_for(
                self._drain_message_queue(), timeout=self.settings.shutdown_timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning("Drain timeout (%ds)", self.settings.shutdown_timeout_seconds)

        if self._health_server:
            await self._health_server.cleanup()
        if self.media_downloader:
            await self.media_downloader.close()
        if self.db_pool:
            await self.db_pool.close()
        if self.cache:
            self.cache.clear()

        await super().close()
        logger.info("Shutdown complete")

    async def _drain_message_queue(self):
        pending = [
            t for t in asyncio.all_tasks() if not t.done() and "on_message" in str(t.get_coro())
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    async def on_error(self, event_method: str, *args, **kwargs):
        error = sys.exc_info()[1]
        logger.exception("Error in %s", event_method)
        if self.notifier and (server_id := self._extract_server_id(args)):
            await self.notifier.notify_error(server_id, error, f"Event: {event_method}")

    def _extract_server_id(self, args) -> Optional[int]:
        for arg in args:
            if hasattr(arg, "guild") and arg.guild:
                return arg.guild.id
            if hasattr(arg, "guild_id") and arg.guild_id:
                return arg.guild_id
            if isinstance(arg, discord.Guild):
                return arg.id

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ):
        cmd_name = interaction.command.name if interaction.command else "unknown"
        logger.exception("App command error: %s", cmd_name)
        if self.notifier and interaction.guild_id:
            ctx = f"Command: /{cmd_name}" if interaction.command else "Unknown command"
            await self.notifier.notify_error(
                interaction.guild_id,
                error,
                ctx,
                user_id=interaction.user.id,
                channel_id=interaction.channel_id,
            )
        if interaction.response.is_done():
            await interaction.followup.send("An error occurred.", ephemeral=True)
        else:
            await interaction.response.send_message("An error occurred.", ephemeral=True)
