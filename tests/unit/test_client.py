"""Tests for bot client functionality."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.database_url = "postgresql://test:test@localhost/test"
    settings.db_pool_min_size = 1
    settings.db_pool_max_size = 5
    settings.cache_max_size = 100
    settings.cache_default_ttl = 60
    settings.feature_media_download = False
    settings.feature_notifiarr_monitoring = False
    settings.health_check_port = 8080
    settings.rate_limit_user_capacity = 10
    settings.rate_limit_server_capacity = 100
    settings.shutdown_timeout_seconds = 5
    settings.media_storage_path = "/tmp/media"
    return settings


class TestFFOBotInit:
    """Tests for FFOBot initialization."""

    def test_bot_initialization(self, mock_settings):
        """Test bot instance creation."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        assert bot.settings == mock_settings
        assert bot.db_pool is None
        assert bot.cache is None
        assert bot.metrics is None
        assert bot.phrase_matcher is None
        assert bot.media_downloader is None
        assert bot.notifiarr_monitor is None
        assert bot.permission_checker is None
        assert bot.rate_limiter is None
        assert bot._health_server is None

    def test_bot_is_shutting_down_initially_false(self, mock_settings):
        """Test shutdown flag is initially False."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        assert bot.is_shutting_down() is False

    def test_bot_has_correct_intents(self, mock_settings):
        """Test bot is configured with correct intents."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        assert bot.intents.message_content is True
        assert bot.intents.guilds is True
        assert bot.intents.members is True
        assert bot.intents.reactions is True


class TestFFOBotLifecycle:
    """Tests for FFOBot lifecycle management."""

    @pytest.mark.asyncio
    async def test_drain_message_queue_no_pending(self, mock_settings):
        """Test draining message queue with no pending tasks."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        await bot._drain_message_queue()

    @pytest.mark.asyncio
    async def test_close_sets_shutdown_flag(self, mock_settings):
        """Test that close sets the shutdown flag."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        bot.db_pool = None
        bot.cache = None
        bot.metrics = None
        bot.media_downloader = None
        bot._health_server = None

        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()

        assert bot.is_shutting_down() is True

    @pytest.mark.asyncio
    async def test_close_with_resources(self, mock_settings):
        """Test close cleans up resources."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        mock_db_pool = AsyncMock()
        mock_cache = MagicMock()
        mock_metrics = MagicMock()
        mock_media_downloader = AsyncMock()
        mock_health_server = AsyncMock()

        bot.db_pool = mock_db_pool
        bot.cache = mock_cache
        bot.metrics = mock_metrics
        bot.media_downloader = mock_media_downloader
        bot._health_server = mock_health_server

        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()

        mock_db_pool.close.assert_called_once()
        mock_cache.clear.assert_called_once()
        mock_media_downloader.close.assert_called_once()
        mock_health_server.cleanup.assert_called_once()
        mock_metrics.set_connection_status.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_close_handles_drain_timeout(self, mock_settings):
        """Test close handles message drain timeout."""
        from bot.client import FFOBot

        mock_settings.shutdown_timeout_seconds = 0.1

        bot = FFOBot(mock_settings)
        bot.db_pool = None
        bot.cache = None
        bot.metrics = None
        bot.media_downloader = None
        bot._health_server = None

        async def slow_drain():
            await asyncio.sleep(10)

        with patch.object(bot, "_drain_message_queue", side_effect=slow_drain):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()

        assert bot.is_shutting_down() is True


class TestFFOBotGuildEvents:
    """Tests for FFOBot guild event handling."""

    @pytest.mark.asyncio
    async def test_register_server(self, mock_settings):
        """Test server registration in database."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()
        bot.db_pool = mock_pool

        mock_guild = MagicMock()
        mock_guild.id = 123456789
        mock_guild.name = "Test Server"

        await bot._register_server(mock_guild)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert mock_guild.id in call_args[0]
        assert mock_guild.name in call_args[0]

    @pytest.mark.asyncio
    async def test_register_server_handles_error(self, mock_settings):
        """Test server registration handles database errors gracefully."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("Database error")
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()
        bot.db_pool = mock_pool

        mock_guild = MagicMock()
        mock_guild.id = 123456789
        mock_guild.name = "Test Server"

        await bot._register_server(mock_guild)

    @pytest.mark.asyncio
    async def test_on_guild_join(self, mock_settings):
        """Test guild join event handling."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        bot._guilds = {1: MagicMock(), 2: MagicMock()}
        bot.metrics = MagicMock()

        with patch.object(bot, "_register_server", new_callable=AsyncMock) as mock_register:
            mock_guild = MagicMock()
            mock_guild.id = 123456789
            mock_guild.name = "New Server"

            await bot.on_guild_join(mock_guild)

            mock_register.assert_called_once_with(mock_guild)
            bot.metrics.set_guild_count.assert_called()

    @pytest.mark.asyncio
    async def test_on_guild_remove(self, mock_settings):
        """Test guild remove event handling."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        bot._guilds = {1: MagicMock()}
        bot.metrics = MagicMock()

        mock_guild = MagicMock()
        mock_guild.id = 123456789
        mock_guild.name = "Removed Server"

        await bot.on_guild_remove(mock_guild)

        bot.metrics.set_guild_count.assert_called()

    @pytest.mark.asyncio
    async def test_on_guild_join_without_metrics(self, mock_settings):
        """Test guild join event without metrics initialized."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        bot._guilds = {}
        bot.metrics = None

        with patch.object(bot, "_register_server", new_callable=AsyncMock):
            mock_guild = MagicMock()
            mock_guild.id = 123456789
            mock_guild.name = "New Server"

            await bot.on_guild_join(mock_guild)

    @pytest.mark.asyncio
    async def test_on_guild_remove_without_metrics(self, mock_settings):
        """Test guild remove event without metrics initialized."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        bot._guilds = {}
        bot.metrics = None

        mock_guild = MagicMock()
        mock_guild.id = 123456789
        mock_guild.name = "Removed Server"

        await bot.on_guild_remove(mock_guild)


class TestFFOBotExtensions:
    """Tests for FFOBot extension loading."""

    @pytest.mark.asyncio
    async def test_load_extensions_success(self, mock_settings):
        """Test successful extension loading."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()

            assert mock_load.call_count == 6

    @pytest.mark.asyncio
    async def test_load_extensions_handles_failure(self, mock_settings):
        """Test extension loading handles failures gracefully."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        async def fail_on_first(*args, **kwargs):
            if "messages" in args[0]:
                raise Exception("Load failed")

        with patch.object(bot, "load_extension", side_effect=fail_on_first):
            await bot._load_extensions()


class TestFFOBotOnReady:
    """Tests for FFOBot on_ready event."""

    @pytest.mark.asyncio
    async def test_on_ready_with_guilds(self, mock_settings):
        """Test on_ready registers guilds and updates metrics."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        mock_guild1 = MagicMock()
        mock_guild1.id = 111
        mock_guild1.name = "Guild 1"

        mock_guild2 = MagicMock()
        mock_guild2.id = 222
        mock_guild2.name = "Guild 2"

        bot.metrics = MagicMock()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock()
        bot._connection.user.id = 123456789
        bot._connection.user.__str__ = lambda self: "TestBot#1234"

        with patch.object(
            FFOBot, "guilds", new_callable=PropertyMock, return_value=[mock_guild1, mock_guild2]
        ):
            with patch.object(bot, "_register_server", new_callable=AsyncMock) as mock_register:
                await bot.on_ready()

                assert mock_register.call_count == 2
                bot.metrics.set_guild_count.assert_called_with(2)
                bot.metrics.set_connection_status.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_on_ready_without_metrics(self, mock_settings):
        """Test on_ready works without metrics initialized."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        bot.metrics = None
        bot._connection = MagicMock()
        bot._connection.user = MagicMock()
        bot._connection.user.id = 123456789
        bot._connection.user.__str__ = lambda self: "TestBot#1234"

        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=[]):
            await bot.on_ready()


class TestFFOBotDrainQueue:
    """Tests for FFOBot message queue draining."""

    @pytest.mark.asyncio
    async def test_drain_message_queue_with_pending_tasks(self, mock_settings):
        """Test draining message queue with pending message tasks."""
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)

        async def fake_on_message():
            await asyncio.sleep(0.1)

        task = asyncio.create_task(fake_on_message())

        with patch("asyncio.all_tasks", return_value={task}):
            await bot._drain_message_queue()

        assert task.done()
