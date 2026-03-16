import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
        assert bot.intents.bans is True


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
        caplog.set_level(logging.WARNING, logger="bot.client")
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
    async def test_close_closes_pool_when_present(self, bot):
        bot.db_pool = AsyncMock()
        bot.cache = MagicMock()
        bot.media_downloader = None
        bot._health_server = None
        bot.pool = MagicMock(close=AsyncMock())
        with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
            with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
                await bot.close()
        bot.pool.close.assert_awaited_once()


class TestFFOBotDrainQueue:
    @pytest.mark.asyncio
    async def test_drain_with_pending_tasks(self, bot):
        async def fake_on_message():
            await asyncio.sleep(0.001)

        task = asyncio.create_task(fake_on_message())
        bot._message_handler_tasks.add(task)
        await bot._drain_message_queue()
        assert task.done()
