from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


class TestFFOBotSetupHook:
    @pytest.mark.asyncio
    async def test_setup_hook_raises_when_no_database_url(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.database_url = None
        bot = FFOBot(mock_settings)
        with pytest.raises(ValueError, match="Database URL not configured"):
            await bot.setup_hook()

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
            patch("bot.processors.media_downloader.MediaDownloader", return_value=mock_downloader),
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
            patch("bot.processors.voice_transcriber.VoiceTranscriber", mock_vt),
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
    async def test_setup_hook_with_minecraft_whitelist(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_minecraft_whitelist = True
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
            patch("bot.services.minecraft_rcon.MinecraftRCONClient"),
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

        assert bot.minecraft_rcon is not None

    @pytest.mark.asyncio
    async def test_setup_hook_with_music(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.lavalink_host = "127.0.0.1"
        mock_settings.lavalink_port = 2333
        mock_settings.lavalink_password = "youshallnotpass"
        bot = FFOBot(mock_settings)

        mock_pool = MagicMock(create_node=AsyncMock())
        patches = [
            patch(
                "bot.client.DatabasePool.create", new_callable=AsyncMock, return_value=MagicMock()
            ),
            patch("bot.client.InMemoryCache"),
            patch("bot.client.BotMetrics"),
            patch("bot.client.PhraseMatcher"),
            patch("bot.client.PermissionChecker"),
            patch("bot.client.RateLimiter"),
            patch("mafic.NodePool", return_value=mock_pool),
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

        assert bot.pool is not None
        mock_pool.create_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_hook_music_disabled_without_password(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.lavalink_password = None
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

        assert bot.pool is None

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
