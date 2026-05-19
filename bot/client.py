from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import TYPE_CHECKING, cast

import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from bot.auth.permissions import PermissionChecker
from bot.cache.memory import InMemoryCache
from bot.processors.phrase_matcher import PhraseMatcher
from bot.utils.health import HealthCheckServer
from bot.utils.http_session import close_session, create_session, set_session
from bot.utils.interaction import send_ephemeral
from bot.utils.metrics import BotMetrics
from bot.utils.notifier import AdminNotifier
from bot.utils.rate_limiter import RateLimiter
from bot.utils.telemetry import shutdown_tracing
from config.settings import Settings
from database.connection import DatabasePool

if TYPE_CHECKING:
    from mafic import NodePool

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


def _parse_discord_shard_ids(raw: str | None) -> list[int] | None:
    if not raw or not raw.strip():
        return None
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _discord_intents() -> discord.Intents:
    intents = discord.Intents.default()
    for k in ("message_content", "guilds", "members", "reactions", "bans", "voice_states"):
        setattr(intents, k, True)
    return intents


class _FFOBotMixin(commands.Bot):
    settings: Settings
    db_pool: DatabasePool | None
    cache: InMemoryCache | None
    metrics: BotMetrics | None
    phrase_matcher: PhraseMatcher | None
    voice_transcriber: object | None
    permission_checker: PermissionChecker | None
    rate_limiter: RateLimiter | None
    notifier: AdminNotifier | None
    minecraft_rcon: object | None
    pool: NodePool | None
    _lavalink_node_created: bool
    _shutdown_event: asyncio.Event
    _health_server: web.AppRunner | None
    _message_handler_tasks: set[asyncio.Task]

    def _init_ffobot_state(self, settings: Settings) -> None:
        self.settings = settings
        self.db_pool = None
        self.cache = None
        self.metrics = None
        self.phrase_matcher = None
        self.voice_transcriber = None
        self.permission_checker = None
        self.rate_limiter = None
        self.notifier = None
        self.minecraft_rcon = None
        self.pool = None
        self._lavalink_node_created = False
        self._shutdown_event = asyncio.Event()
        self._health_server = None
        self._message_handler_tasks = set()

    async def setup_hook(self):
        with _tracer.start_as_current_span("bot.setup_hook"):
            logger.info("Initializing...")
            db_url = self.settings.database_url
            if not db_url:
                raise ValueError("Database URL not configured")
            self.metrics = BotMetrics()
            self.db_pool = await DatabasePool.create(
                db_url,
                min_size=self.settings.db_pool_min_size,
                max_size=self.settings.db_pool_max_size,
                connection_timeout=self.settings.db_connection_timeout,
                acquire_timeout=self.settings.db_acquire_timeout,
                metrics=self.metrics,
            )
            max_memory_bytes = (
                int(self.settings.cache_max_memory_mb * 1024 * 1024)
                if self.settings.cache_max_memory_mb > 0
                else 0
            )
            self.cache = InMemoryCache(
                max_size=self.settings.cache_max_size,
                default_ttl=self.settings.cache_default_ttl,
                max_memory_bytes=max_memory_bytes,
            )
            set_session(create_session())

            self.phrase_matcher = PhraseMatcher(self.db_pool, self.cache)

            if self.settings.feature_voice_transcription and self.settings.openai_api_key:
                from bot.processors.voice_transcriber import VoiceTranscriber

                vt = VoiceTranscriber(api_key=self.settings.openai_api_key)
                self.voice_transcriber = vt

            assert self.db_pool is not None and self.cache is not None
            self.permission_checker = PermissionChecker(self.db_pool, self.cache, self)
            self.rate_limiter = RateLimiter(
                user_capacity=self.settings.rate_limit_user_capacity,
                server_capacity=self.settings.rate_limit_server_capacity,
            )
            self.notifier = AdminNotifier(self)
            from bot.utils.edit_tracker import EditTracker

            self.edit_tracker = EditTracker()
            if self.settings.feature_minecraft_whitelist:
                from bot.services.minecraft_rcon import MinecraftRCONClient

                rcon = MinecraftRCONClient(self.settings)
                self.minecraft_rcon = rcon
            if self.settings.feature_music and self.settings.lavalink_password:
                from mafic import NodePool

                self.pool = NodePool(self)
            self.tree.on_error = self._on_app_command_error

            await self._start_health_server()
            await self._load_extensions()
            await self._register_persistent_views()
            logger.info("Ready")

    async def _load_extensions(self):
        extensions = [
            "bot.commands.help_cmd",
            "bot.handlers.messages",
            "bot.handlers.reactions",
            "bot.handlers.moderation",
            "bot.handlers.edit_tracking",
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
        if (
            self.settings.feature_minecraft_whitelist
            and self.settings.whitelist_cache_reconcile_interval_hours > 0
        ):
            extensions.append("bot.tasks.whitelist_cache_reconcile")
        for ext, enabled in [
            ("bot.commands.quotebook", self.settings.feature_quotebook),
            ("bot.commands.whitelist", self.settings.feature_minecraft_whitelist),
            ("bot.commands.faq", self.settings.feature_faq),
            ("bot.commands.music", self.settings.feature_music),
        ]:
            if enabled:
                extensions.append(ext)

        with _tracer.start_as_current_span("bot.load_extensions"):
            for extension in extensions:
                with _tracer.start_as_current_span(
                    "bot.load_extension",
                    attributes={"extension.module": extension},
                ) as ext_span:
                    try:
                        await self.load_extension(extension)
                    except Exception as e:
                        ext_span.record_exception(e)
                        logger.error("Failed to load extension %s: %s", extension, e, exc_info=True)

    async def _start_health_server(self):
        public_key = (
            self.settings.discord_public_key
            if self.settings.interactions_endpoint_enabled
            else None
        )
        health_server = HealthCheckServer(
            self,
            port=self.settings.health_check_port,
            public_key=public_key,
            host=self.settings.health_check_host,
        )
        await health_server.start()
        self._health_server = health_server.runner

    async def _register_persistent_views(self):
        if not self.db_pool:
            return
        if self.settings.feature_giveaways:
            from bot.commands.giveaway import GiveawayView
            from bot.tasks.giveaway_manager import CloseGiveawayThreadView

            self.add_view(CloseGiveawayThreadView(host_id=0))

            async with self.db_pool.acquire() as conn:
                active = await conn.fetch("""
                    SELECT g.id, g.message_id, COUNT(ge.user_id)::int AS entry_count
                    FROM giveaways g
                    LEFT JOIN giveaway_entries ge ON ge.giveaway_id = g.id
                    WHERE g.is_active = true AND g.message_id IS NOT NULL
                    GROUP BY g.id, g.message_id
                    """)
                for row in active:
                    self.add_view(
                        GiveawayView(row["id"], self, entry_count=row["entry_count"] or 0),
                        message_id=row["message_id"],
                    )

    async def on_shard_ready(self, shard_id: int):
        if (getattr(self, "shard_count", None) or 0) > 1:
            logger.info("Shard %s connected", shard_id)

    async def on_ready(self):
        if (getattr(self, "shard_count", None) or 0) > 1 and not self.is_ready():
            return

        logger.info(
            "Connected as %s (ID: %s) to %d servers", self.user, self.user.id, len(self.guilds)
        )

        if self.pool and not self._lavalink_node_created:
            self._lavalink_node_created = True
            try:
                await self.pool.create_node(
                    host=self.settings.lavalink_host,
                    port=self.settings.lavalink_port,
                    password=self.settings.lavalink_password,
                    label="main",
                )
            except Exception as e:
                logger.warning("Lavalink connection failed, music disabled: %s", e)
                self.pool = None

        if self.pool and self.db_pool and getattr(self.settings, "feature_music", False):
            try:
                from bot.commands.music import reconnect_music_voice_after_ready

                await reconnect_music_voice_after_ready(self)
            except Exception as e:
                logger.warning("Music voice recovery failed: %s", e, exc_info=True)

        if getattr(self.settings, "sync_commands_on_boot", True):
            with _tracer.start_as_current_span("discord.sync_commands") as sync_span:
                sync_span.set_attribute("discord.guild_count", len(self.guilds))
                clear_commands_on_boot = getattr(self.settings, "clear_commands_on_boot", True)
                if clear_commands_on_boot:
                    await self._connection.http.bulk_upsert_global_commands(self.application_id, [])
                if self.guilds:
                    await asyncio.gather(*[self._register_server(g) for g in self.guilds])
                for guild in self.guilds:
                    if clear_commands_on_boot:
                        await self._connection.http.bulk_upsert_guild_commands(
                            self.application_id, guild.id, []
                        )
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
        if not self.db_pool:
            return
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
        if self.settings.bot_owner_server_id and self.settings.bot_owner_notify_channel_id:
            owner_ch = self.get_channel(self.settings.bot_owner_notify_channel_id)
            if (
                owner_ch
                and getattr(getattr(owner_ch, "guild", None), "id", None)
                == self.settings.bot_owner_server_id
            ):
                try:
                    embed = discord.Embed(
                        title="Bot Added to Server",
                        description=guild.name,
                        color=discord.Color.green(),
                    )
                    embed.add_field(name="Server ID", value=str(guild.id), inline=True).add_field(
                        name="Members", value=str(guild.member_count or 0), inline=True
                    )
                    await owner_ch.send(embed=embed)
                except Exception as e:
                    logger.warning("Failed to notify owner of new server: %s", e)

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
        await close_session()
        if self.db_pool:
            await self.db_pool.close()
        if self.cache:
            self.cache.clear()
        if self.pool:
            await self.pool.close()

        await super().close()
        shutdown_tracing()
        logger.info("Shutdown complete")

    async def _drain_message_queue(self):
        pending = list(self._message_handler_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    async def on_error(self, event_method: str, *args, **kwargs):
        error = sys.exc_info()[1]
        logger.exception("Error in %s", event_method)
        if self.notifier and (server_id := self._extract_server_id(args)):
            exc = error if isinstance(error, Exception) else RuntimeError(str(error))
            await self.notifier.notify_error(server_id, exc, f"Event: {event_method}")

    def _extract_server_id(self, args: tuple[object, ...]) -> int | None:
        for arg in args:
            if hasattr(arg, "guild") and arg.guild:
                return int(getattr(arg.guild, "id", 0))
            if hasattr(arg, "guild_id") and arg.guild_id:
                return int(arg.guild_id)
            if isinstance(arg, discord.Guild):
                return int(arg.id)
        return None

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
        await send_ephemeral(interaction, "An error occurred.")


class MetricsCommandTree(app_commands.CommandTree):
    async def _call(self, interaction: discord.Interaction) -> None:
        bot = cast(_FFOBotMixin, self.client)
        start = time.perf_counter()
        server_id = str(interaction.guild_id) if interaction.guild_id else "0"
        data = interaction.data or {}
        if data.get("type", 1) == 1:
            command, _ = self._get_app_command_options(data)
            command_name = command.qualified_name if command else "unknown"
        else:
            command_name = data.get("name", "unknown")

        with _tracer.start_as_current_span("discord.interaction") as span:
            span.set_attribute("discord.command", command_name)
            span.set_attribute("discord.guild_id", server_id)
            if interaction.channel_id:
                span.set_attribute("discord.channel_id", str(interaction.channel_id))
            span.set_attribute("discord.user_id", str(interaction.user.id))
            try:
                if bot.rate_limiter and interaction.guild_id:
                    allowed, reason = await bot.rate_limiter.check_rate_limit(
                        interaction.user.id, interaction.guild_id
                    )
                    if not allowed:
                        span.set_attribute("discord.rate_limited", True)
                        if bot.settings.feature_notify_rate_limit and bot.notifier:
                            await bot.notifier.notify_rate_limit_hit(
                                interaction.guild_id,
                                interaction.user.id,
                                reason,
                                command_name,
                            )
                        await send_ephemeral(interaction, reason)
                        interaction.command_failed = True
                        return

                await super()._call(interaction)
            finally:
                if getattr(interaction, "command_failed", False):
                    span.set_status(Status(StatusCode.ERROR))
                if bot.metrics:
                    status = "error" if getattr(interaction, "command_failed", False) else "success"
                    bot.metrics.commands_executed.labels(
                        command_name=command_name,
                        server_id=server_id,
                        status=status,
                    ).inc()
                    bot.metrics.command_duration.labels(command_name=command_name).observe(
                        time.perf_counter() - start
                    )


class FFOBot(_FFOBotMixin):
    def __init__(self, settings: Settings):
        super().__init__(
            command_prefix="!",
            intents=_discord_intents(),
            help_command=None,
            tree_cls=MetricsCommandTree,
        )
        self._init_ffobot_state(settings)


class FFOShardedBot(_FFOBotMixin, commands.AutoShardedBot):
    def __init__(self, settings: Settings):
        shard_ids = _parse_discord_shard_ids(settings.discord_shard_ids)
        super().__init__(
            command_prefix="!",
            intents=_discord_intents(),
            help_command=None,
            tree_cls=MetricsCommandTree,
            shard_count=settings.discord_shard_count,
            shard_ids=shard_ids,
        )
        self._init_ffobot_state(settings)


def create_ffo_bot(settings: Settings) -> FFOBot | FFOShardedBot:
    if settings.discord_sharding_enabled:
        return FFOShardedBot(settings)
    return FFOBot(settings)
