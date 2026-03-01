import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, patch

import discord
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
            with patch.object(bot.tree, "copy_global_to"):
                with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                    guild = MagicMock(id=123, name="New")
                    await bot.on_guild_join(guild)
                    mock_reg.assert_called_once_with(guild)
                    bot.tree.copy_global_to.assert_called_once_with(guild=guild)
                    bot.tree.sync.assert_called_once_with(guild=guild)
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
            with patch.object(bot.tree, "copy_global_to"):
                with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                    await bot.on_guild_join(MagicMock(id=123, name="New"))
        await bot.on_guild_remove(MagicMock(id=123, name="Removed"))


class TestFFOBotExtensions:
    @pytest.mark.asyncio
    async def test_load_extensions_success(self, bot):
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            assert mock_load.call_count == 11

    @pytest.mark.asyncio
    async def test_load_extensions_handles_failure(self, bot):
        async def fail_on_messages(*args):
            if "messages" in args[0]:
                raise Exception("Load failed")

        with patch.object(bot, "load_extension", side_effect=fail_on_messages):
            await bot._load_extensions()


class TestFFOBotPersistentViews:
    @pytest.mark.asyncio
    async def test_register_persistent_views_enabled(self, bot):
        import uuid
        bot.settings.feature_giveaways = True
        gid, mid = uuid.uuid4(), 12345
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[{"id": gid, "message_id": mid}])
        conn.fetchval = AsyncMock(return_value=0)
        bot.db_pool = make_db_ctx(conn)
        with patch("bot.commands.giveaway.GiveawayView"):
            with patch.object(bot, "add_view") as mock_add:
                await bot._register_persistent_views()
                mock_add.assert_called_once()
                mock_add.assert_called_with(ANY, message_id=mid)

    @pytest.mark.asyncio
    async def test_register_persistent_views_disabled(self, bot):
        bot.settings.feature_giveaways = False
        with patch.object(bot, "add_view") as mock_add:
            await bot._register_persistent_views()
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_persistent_views_no_active(self, bot):
        bot.settings.feature_giveaways = True
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[])
        bot.db_pool = make_db_ctx(conn)
        with patch.object(bot, "add_view") as mock_add:
            await bot._register_persistent_views()
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_persistent_views_multiple(self, bot):
        import uuid
        bot.settings.feature_giveaways = True
        rows = [
            {"id": uuid.uuid4(), "message_id": 111},
            {"id": uuid.uuid4(), "message_id": 222},
            {"id": uuid.uuid4(), "message_id": 333},
        ]
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.fetchval = AsyncMock(return_value=0)
        bot.db_pool = make_db_ctx(conn)
        with patch("bot.commands.giveaway.GiveawayView"):
            with patch.object(bot, "add_view") as mock_add:
                await bot._register_persistent_views()
                assert mock_add.call_count == 3
                message_ids = [c.kwargs["message_id"] for c in mock_add.call_args_list]
                assert message_ids == [111, 222, 333]


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
                with patch.object(bot.tree, "copy_global_to"):
                    with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                        await bot.on_ready()
                        assert mock_reg.call_count == 2
                        assert bot.tree.copy_global_to.call_count == 2
                        assert bot.tree.sync.call_count == 2
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
            await asyncio.sleep(0.001)

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

    @pytest.mark.asyncio
    async def test_setup_hook_with_voice_transcription(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_voice_transcription = True
        mock_settings.openai_api_key = "sk-test"
        bot = FFOBot(mock_settings)

        mock_vt = MagicMock()
        patches = [
            patch(
                "bot.client.DatabasePool.create", new_callable=AsyncMock, return_value=MagicMock()
            ),
            patch("bot.client.InMemoryCache"),
            patch("bot.client.BotMetrics"),
            patch("bot.client.PhraseMatcher"),
            patch("bot.client.PermissionChecker"),
            patch("bot.client.RateLimiter"),
            patch("bot.client.VoiceTranscriber", mock_vt),
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

        mock_vt.assert_called_once_with(api_key="sk-test")
        assert bot.voice_transcriber is not None

    @pytest.mark.asyncio
    async def test_setup_hook_voice_transcription_disabled_without_api_key(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_voice_transcription = True
        mock_settings.openai_api_key = None
        bot = FFOBot(mock_settings)

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

        assert bot.voice_transcriber is None


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


class TestFFOBotErrorHandlers:
    @pytest.mark.asyncio
    async def test_on_error_with_server(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        with patch("sys.exc_info", return_value=(ValueError, ValueError("test"), None)):
            await bot.on_error("on_message", MagicMock(guild=MagicMock(id=123)))
        assert bot.notifier.notify_error.call_args[0][0] == 123

    @pytest.mark.asyncio
    async def test_on_error_no_server(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        with patch("sys.exc_info", return_value=(ValueError, ValueError("test"), None)):
            await bot.on_error("on_message")
        bot.notifier.notify_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_error_no_notifier(self, bot):
        bot.notifier = None
        with patch("sys.exc_info", return_value=(ValueError, ValueError("test"), None)):
            await bot.on_error("on_message", MagicMock(guild=MagicMock(id=123)))

    def test_extract_server_id(self, bot):
        assert bot._extract_server_id([MagicMock(guild=MagicMock(id=123))]) == 123
        obj = MagicMock(spec=["guild_id"])
        obj.guild_id = 456
        assert bot._extract_server_id([obj]) == 456
        guild = MagicMock(spec=discord.Guild, id=789)
        assert bot._extract_server_id([guild]) == 789
        assert bot._extract_server_id([]) is None
        assert bot._extract_server_id([MagicMock(spec=[])]) is None

    def test_extract_server_id_guild_id_no_guild(self, bot):
        obj = MagicMock()
        obj.guild = None
        obj.guild_id = 111
        assert bot._extract_server_id([obj]) == 111

    def test_extract_server_id_first_match_wins(self, bot):
        a = MagicMock(guild=MagicMock(id=1))
        b = MagicMock(guild=MagicMock(id=2))
        assert bot._extract_server_id([a, b]) == 1


class TestFFOBotAppCommandError:
    def make_interaction(self, guild_id=123, done=False, command="test"):
        i = MagicMock()
        i.guild_id = guild_id
        i.user.id = 456
        i.channel_id = 789
        i.command = MagicMock(name=command) if command else None
        i.response.is_done.return_value = done
        i.response.send_message = AsyncMock()
        i.followup.send = AsyncMock()
        return i

    @pytest.mark.asyncio
    async def test_notifies_and_responds(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        i = self.make_interaction()
        await bot._on_app_command_error(i, discord.app_commands.AppCommandError())
        bot.notifier.notify_error.assert_called_once()
        i.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_followup_when_done(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        i = self.make_interaction(done=True)
        await bot._on_app_command_error(i, discord.app_commands.AppCommandError())
        i.followup.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_guild_skips_notify(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        i = self.make_interaction(guild_id=None)
        await bot._on_app_command_error(i, discord.app_commands.AppCommandError())
        bot.notifier.notify_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_command_uses_unknown(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        i = self.make_interaction(command=None)
        await bot._on_app_command_error(i, discord.app_commands.AppCommandError())
        assert "Unknown" in bot.notifier.notify_error.call_args[0][2]

    @pytest.mark.asyncio
    async def test_app_command_error_response_done_uses_followup(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        i = self.make_interaction(done=True, command=None)
        await bot._on_app_command_error(i, discord.app_commands.AppCommandError())
        i.followup.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_command_error_response_not_done_uses_response(self, bot):
        bot.notifier = MagicMock(notify_error=AsyncMock())
        i = self.make_interaction(done=False, command=None)
        await bot._on_app_command_error(i, discord.app_commands.AppCommandError())
        i.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_no_notifier(self, bot):
        bot.notifier = None
        with patch("sys.exc_info", return_value=(ValueError, ValueError("x"), None)):
            await bot.on_error("on_message", MagicMock(guild=MagicMock(id=123)))

    @pytest.mark.asyncio
    async def test_close_media_downloader_none(self, bot):
        bot.db_pool = AsyncMock()
        bot.cache = MagicMock()
        bot.media_downloader = None
        bot._health_server = None
        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()
        bot.db_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_db_pool_none(self, bot):
        bot.db_pool = None
        bot.cache = MagicMock()
        bot.media_downloader = None
        bot._health_server = None
        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()

    @pytest.mark.asyncio
    async def test_close_cache_none(self, bot):
        bot.db_pool = AsyncMock()
        bot.cache = None
        bot.media_downloader = None
        bot._health_server = None
        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()

    @pytest.mark.asyncio
    async def test_register_persistent_views_acquire_raises(self, bot):
        bot.settings.feature_giveaways = True
        bot.db_pool = MagicMock()
        bot.db_pool.acquire = MagicMock(side_effect=Exception("DB"))
        with pytest.raises(Exception, match="DB"):
            await bot._register_persistent_views()

    @pytest.mark.asyncio
    async def test_on_ready_empty_guilds(self, bot):
        from bot.client import FFOBot

        bot.metrics = MagicMock()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock(id=123)
        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=[]):
            await bot.on_ready()
        bot.metrics.set_guild_count.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_load_extensions_multiple_failures(self, bot, caplog):
        async def fail_all(*args):
            raise Exception("load failed")

        with patch.object(bot, "load_extension", side_effect=fail_all):
            await bot._load_extensions()
        assert caplog.text.count("load failed") >= 1
