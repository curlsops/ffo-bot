import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.database_url = "postgresql://test:test@localhost/test"
    s.db_pool_min_size = 1
    s.db_pool_max_size = 5
    s.cache_max_size = 100
    s.cache_default_ttl = 60
    s.feature_media_download = False
    s.health_check_port = 8080
    s.rate_limit_user_capacity = 10
    s.rate_limit_server_capacity = 100
    s.shutdown_timeout_seconds = 5
    s.media_storage_path = "/tmp/media"
    return s


@pytest.fixture
def bot(mock_settings):
    from bot.client import FFOBot

    return FFOBot(mock_settings)


def make_db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


class TestFFOBotInit:
    def test_initialization(self, bot, mock_settings):
        assert bot.settings == mock_settings
        assert bot.db_pool is None
        assert bot.cache is None
        assert bot.metrics is None
        assert bot.phrase_matcher is None
        assert bot.media_downloader is None
        assert bot.permission_checker is None
        assert bot.rate_limiter is None
        assert bot._health_server is None

    def test_not_shutting_down_initially(self, bot):
        assert bot.is_shutting_down() is False

    def test_intents(self, bot):
        assert bot.intents.message_content is True
        assert bot.intents.guilds is True
        assert bot.intents.members is True
        assert bot.intents.reactions is True


class TestFFOBotLifecycle:
    @pytest.mark.asyncio
    async def test_drain_no_pending(self, bot):
        await bot._drain_message_queue()

    @pytest.mark.asyncio
    async def test_close_sets_shutdown_flag(self, bot):
        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()
        assert bot.is_shutting_down() is True

    @pytest.mark.asyncio
    async def test_close_with_resources(self, bot):
        bot.db_pool = AsyncMock()
        bot.cache = MagicMock()
        bot.metrics = MagicMock()
        bot.media_downloader = AsyncMock()
        bot._health_server = AsyncMock()

        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()

        bot.db_pool.close.assert_called_once()
        bot.cache.clear.assert_called_once()
        bot.media_downloader.close.assert_called_once()
        bot._health_server.cleanup.assert_called_once()
        bot.metrics.set_connection_status.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_close_handles_drain_timeout(self, mock_settings, caplog):
        from bot.client import FFOBot

        mock_settings.shutdown_timeout_seconds = 0.01
        bot = FFOBot(mock_settings)

        async def slow_drain():
            await asyncio.sleep(10)

        with patch.object(bot, "_drain_message_queue", side_effect=slow_drain):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()
        assert bot.is_shutting_down() is True
        assert "Drain timeout" in caplog.text


class TestFFOBotGuildEvents:
    @pytest.mark.asyncio
    async def test_register_server(self, bot):
        conn = AsyncMock()
        bot.db_pool = make_db_ctx(conn)
        guild = MagicMock(id=123456789, name="Test Server")

        await bot._register_server(guild)
        conn.execute.assert_called_once()
        assert guild.id in conn.execute.call_args[0]
        assert guild.name in conn.execute.call_args[0]

    @pytest.mark.asyncio
    async def test_register_server_handles_error(self, bot, caplog):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=Exception("Database error"))
        bot.db_pool = make_db_ctx(conn)

        await bot._register_server(MagicMock(id=123456789, name="Test"))
        assert "Failed to register server 123456789" in caplog.text

    @pytest.mark.asyncio
    async def test_on_guild_join(self, bot):
        bot._guilds = {1: MagicMock(), 2: MagicMock()}
        bot.metrics = MagicMock()

        with patch.object(bot, "_register_server", new_callable=AsyncMock) as mock_reg:
            guild = MagicMock(id=123, name="New")
            await bot.on_guild_join(guild)
            mock_reg.assert_called_once_with(guild)
            bot.metrics.set_guild_count.assert_called()

    @pytest.mark.asyncio
    async def test_on_guild_remove(self, bot):
        bot._guilds = {1: MagicMock()}
        bot.metrics = MagicMock()
        await bot.on_guild_remove(MagicMock(id=123, name="Removed"))
        bot.metrics.set_guild_count.assert_called()

    @pytest.mark.asyncio
    async def test_guild_events_without_metrics(self, bot):
        bot._guilds = {}
        bot.metrics = None
        with patch.object(bot, "_register_server", new_callable=AsyncMock):
            await bot.on_guild_join(MagicMock(id=123, name="New"))
        await bot.on_guild_remove(MagicMock(id=123, name="Removed"))


class TestFFOBotExtensions:
    @pytest.mark.asyncio
    async def test_load_extensions_success(self, bot):
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            assert mock_load.call_count == 6

    @pytest.mark.asyncio
    async def test_load_extensions_handles_failure(self, bot):
        async def fail_on_messages(*args):
            if "messages" in args[0]:
                raise Exception("Load failed")

        with patch.object(bot, "load_extension", side_effect=fail_on_messages):
            await bot._load_extensions()


class TestFFOBotOnReady:
    @pytest.mark.asyncio
    async def test_on_ready_with_guilds(self, bot):
        from bot.client import FFOBot

        guilds = [MagicMock(id=111, name="G1"), MagicMock(id=222, name="G2")]
        bot.metrics = MagicMock()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock(id=123)
        bot._connection.user.__str__ = lambda s: "Bot#1234"

        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=guilds):
            with patch.object(bot, "_register_server", new_callable=AsyncMock) as mock_reg:
                await bot.on_ready()
                assert mock_reg.call_count == 2
                bot.metrics.set_guild_count.assert_called_with(2)
                bot.metrics.set_connection_status.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_on_ready_without_metrics(self, bot):
        from bot.client import FFOBot

        bot.metrics = None
        bot._connection = MagicMock()
        bot._connection.user = MagicMock(id=123)
        bot._connection.user.__str__ = lambda s: "Bot#1234"

        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=[]):
            await bot.on_ready()


class TestFFOBotDrainQueue:
    @pytest.mark.asyncio
    async def test_drain_with_pending_tasks(self, bot):
        async def fake_on_message():
            await asyncio.sleep(0.1)

        task = asyncio.create_task(fake_on_message())
        with patch("asyncio.all_tasks", return_value={task}):
            await bot._drain_message_queue()
        assert task.done()


class TestFFOBotSetupHook:
    @pytest.mark.asyncio
    async def test_setup_hook_initializes_resources(self, bot):
        patches = [
            patch(
                "bot.client.DatabasePool.create", new_callable=AsyncMock, return_value=MagicMock()
            ),
            patch("bot.client.InMemoryCache"),
            patch("bot.client.BotMetrics"),
            patch("bot.client.PhraseMatcher"),
            patch("bot.client.PermissionChecker"),
            patch("bot.client.RateLimiter"),
            patch.object(bot, "_start_health_server", new_callable=AsyncMock),
            patch.object(bot, "_load_extensions", new_callable=AsyncMock),
        ]
        mock_tree = MagicMock(sync=AsyncMock())

        for p in patches:
            p.start()
        try:
            with patch.object(type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree):
                await bot.setup_hook()
        finally:
            for p in patches:
                p.stop()

        assert bot.db_pool is not None
        assert bot.cache is not None
        assert bot.metrics is not None
        assert bot.phrase_matcher is not None
        assert bot.permission_checker is not None
        assert bot.rate_limiter is not None

    @pytest.mark.asyncio
    async def test_setup_hook_with_media_download(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_media_download = True
        bot = FFOBot(mock_settings)

        mock_downloader = MagicMock(initialize=AsyncMock())
        patches = [
            patch(
                "bot.client.DatabasePool.create", new_callable=AsyncMock, return_value=MagicMock()
            ),
            patch("bot.client.InMemoryCache"),
            patch("bot.client.BotMetrics"),
            patch("bot.client.PhraseMatcher"),
            patch("bot.client.MediaDownloader", return_value=mock_downloader),
            patch("bot.client.PermissionChecker"),
            patch("bot.client.RateLimiter"),
            patch.object(bot, "_start_health_server", new_callable=AsyncMock),
            patch.object(bot, "_load_extensions", new_callable=AsyncMock),
        ]
        mock_tree = MagicMock(sync=AsyncMock())

        for p in patches:
            p.start()
        try:
            with patch.object(type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree):
                await bot.setup_hook()
        finally:
            for p in patches:
                p.stop()

        assert bot.media_downloader is not None
        mock_downloader.initialize.assert_called_once()


class TestFFOBotHealthServer:
    @pytest.mark.asyncio
    async def test_start_health_server(self, bot, mock_settings):
        with patch("bot.utils.health.HealthCheckServer") as mock_cls:
            mock_server = MagicMock(start=AsyncMock(), runner=MagicMock())
            mock_cls.return_value = mock_server

            await bot._start_health_server()

            mock_cls.assert_called_once_with(bot, port=mock_settings.health_check_port)
            mock_server.start.assert_called_once()
            assert bot._health_server == mock_server.runner
