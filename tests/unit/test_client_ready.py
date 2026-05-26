import logging
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest


class TestFFOBotOnReady:
    @pytest.mark.asyncio
    async def test_on_ready_with_guilds(self, bot):
        from bot.client import FFOBot

        guilds = [MagicMock(id=111, name="G1"), MagicMock(id=222, name="G2")]
        bot.metrics = MagicMock()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock(id=123)
        bot._connection.user.__str__ = lambda s: "Bot#1234"
        bot._connection.http.bulk_upsert_global_commands = AsyncMock()
        bot._connection.http.bulk_upsert_guild_commands = AsyncMock()

        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=guilds):
            with patch.object(bot, "_register_server", new_callable=AsyncMock) as mock_reg:
                with patch.object(bot.tree, "copy_global_to") as mock_copy:
                    with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                        await bot.on_ready()
                        bot._connection.http.bulk_upsert_global_commands.assert_awaited_once_with(
                            bot.application_id, []
                        )
                        assert mock_reg.call_count == 2
                        assert bot._connection.http.bulk_upsert_guild_commands.call_count == 2
                        assert mock_copy.call_count == 2
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
        bot._connection.http.bulk_upsert_global_commands = AsyncMock()

        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=[]):
            with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                await bot.on_ready()

    @pytest.mark.asyncio
    async def test_on_ready_skips_sync_when_disabled(self, bot):
        from bot.client import FFOBot

        bot.settings.sync_commands_on_boot = False
        bot.metrics = MagicMock()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock(id=123)
        guilds = [MagicMock(id=111, name="G1")]

        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=guilds):
            with patch.object(bot, "_register_server", new_callable=AsyncMock):
                await bot.on_ready()
        bot._connection.http.bulk_upsert_global_commands.assert_not_called()
        bot._connection.http.bulk_upsert_guild_commands.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_ready_skips_clear_when_disabled(self, bot):
        from bot.client import FFOBot

        bot.settings.sync_commands_on_boot = True
        bot.settings.clear_commands_on_boot = False
        bot.metrics = MagicMock()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock(id=123)
        bot._connection.http.bulk_upsert_global_commands = AsyncMock()
        bot._connection.http.bulk_upsert_guild_commands = AsyncMock()
        guilds = [MagicMock(id=111, name="G1")]

        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=guilds):
            with patch.object(bot, "_register_server", new_callable=AsyncMock) as mock_reg:
                with patch.object(bot.tree, "copy_global_to") as mock_copy:
                    with patch.object(bot.tree, "sync", new_callable=AsyncMock) as mock_sync:
                        await bot.on_ready()

        bot._connection.http.bulk_upsert_global_commands.assert_not_called()
        bot._connection.http.bulk_upsert_guild_commands.assert_not_called()
        mock_reg.assert_awaited_once_with(guilds[0])
        mock_copy.assert_called_once_with(guild=guilds[0])
        mock_sync.assert_awaited_once_with(guild=guilds[0])

    @pytest.mark.asyncio
    async def test_on_ready_empty_guilds(self, bot):
        from bot.client import FFOBot

        bot.metrics = MagicMock()
        bot._connection = MagicMock()
        bot._connection.user = MagicMock(id=123)
        bot._connection.http.bulk_upsert_global_commands = AsyncMock()
        with patch.object(FFOBot, "guilds", new_callable=PropertyMock, return_value=[]):
            with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                await bot.on_ready()
        bot.metrics.set_guild_count.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_on_ready_creates_lavalink_node(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.lavalink_host = "127.0.0.1"
        mock_settings.lavalink_port = 2333
        mock_settings.lavalink_password = "secret"
        bot = FFOBot(mock_settings)
        mock_pool = MagicMock(create_node=AsyncMock())
        bot.pool = mock_pool

        mock_http = MagicMock()
        mock_http.bulk_upsert_global_commands = AsyncMock()
        mock_http.bulk_upsert_guild_commands = AsyncMock()
        mock_conn = MagicMock(http=mock_http)
        with (
            patch.object(discord.Client, "user", PropertyMock(return_value=MagicMock(id=123))),
            patch.object(discord.Client, "guilds", PropertyMock(return_value=[])),
            patch.object(bot, "_register_server", new_callable=AsyncMock),
            patch.object(bot, "_connection", mock_conn),
            patch.object(bot.tree, "copy_global_to"),
            patch.object(bot.tree, "sync", new_callable=AsyncMock),
        ):
            await bot.on_ready()

        mock_pool.create_node.assert_called_once_with(
            host="127.0.0.1", port=2333, password="secret", label="main"
        )

    @pytest.mark.asyncio
    async def test_on_ready_runs_music_voice_recovery(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.lavalink_host = "127.0.0.1"
        mock_settings.lavalink_port = 2333
        mock_settings.lavalink_password = "secret"
        bot = FFOBot(mock_settings)
        mock_pool = MagicMock(create_node=AsyncMock())
        bot.pool = mock_pool
        bot.db_pool = MagicMock()

        mock_http = MagicMock()
        mock_http.bulk_upsert_global_commands = AsyncMock()
        mock_http.bulk_upsert_guild_commands = AsyncMock()
        mock_conn = MagicMock(http=mock_http)
        with (
            patch.object(discord.Client, "user", PropertyMock(return_value=MagicMock(id=123))),
            patch.object(discord.Client, "guilds", PropertyMock(return_value=[])),
            patch.object(bot, "_register_server", new_callable=AsyncMock),
            patch.object(bot, "_connection", mock_conn),
            patch.object(bot.tree, "copy_global_to"),
            patch.object(bot.tree, "sync", new_callable=AsyncMock),
            patch("bot.commands.music.reconnect_music_voice_after_ready", AsyncMock()) as rec,
        ):
            await bot.on_ready()

        mock_pool.create_node.assert_called_once()
        rec.assert_awaited_once_with(bot)

    @pytest.mark.asyncio
    async def test_on_ready_skips_music_voice_recovery_when_disabled(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.music_voice_recovery_on_ready = False
        mock_settings.lavalink_host = "127.0.0.1"
        mock_settings.lavalink_port = 2333
        mock_settings.lavalink_password = "secret"
        bot = FFOBot(mock_settings)
        mock_pool = MagicMock(create_node=AsyncMock())
        bot.pool = mock_pool
        bot.db_pool = MagicMock()

        mock_http = MagicMock()
        mock_http.bulk_upsert_global_commands = AsyncMock()
        mock_http.bulk_upsert_guild_commands = AsyncMock()
        mock_conn = MagicMock(http=mock_http)
        with (
            patch.object(discord.Client, "user", PropertyMock(return_value=MagicMock(id=123))),
            patch.object(discord.Client, "guilds", PropertyMock(return_value=[])),
            patch.object(bot, "_register_server", new_callable=AsyncMock),
            patch.object(bot, "_connection", mock_conn),
            patch.object(bot.tree, "copy_global_to"),
            patch.object(bot.tree, "sync", new_callable=AsyncMock),
            patch("bot.commands.music.reconnect_music_voice_after_ready", AsyncMock()) as rec,
        ):
            await bot.on_ready()

        rec.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_ready_skips_music_voice_recovery_without_db_pool(self, mock_settings):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.lavalink_host = "127.0.0.1"
        mock_settings.lavalink_port = 2333
        mock_settings.lavalink_password = "secret"
        bot = FFOBot(mock_settings)
        mock_pool = MagicMock(create_node=AsyncMock())
        bot.pool = mock_pool
        bot.db_pool = None

        mock_http = MagicMock()
        mock_http.bulk_upsert_global_commands = AsyncMock()
        mock_http.bulk_upsert_guild_commands = AsyncMock()
        mock_conn = MagicMock(http=mock_http)
        with (
            patch.object(discord.Client, "user", PropertyMock(return_value=MagicMock(id=123))),
            patch.object(discord.Client, "guilds", PropertyMock(return_value=[])),
            patch.object(bot, "_register_server", new_callable=AsyncMock),
            patch.object(bot, "_connection", mock_conn),
            patch.object(bot.tree, "copy_global_to"),
            patch.object(bot.tree, "sync", new_callable=AsyncMock),
            patch("bot.commands.music.reconnect_music_voice_after_ready", AsyncMock()) as rec,
        ):
            await bot.on_ready()

        rec.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_ready_music_voice_recovery_failure_logged(self, mock_settings, caplog):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.lavalink_host = "127.0.0.1"
        mock_settings.lavalink_port = 2333
        mock_settings.lavalink_password = "secret"
        bot = FFOBot(mock_settings)
        mock_pool = MagicMock(create_node=AsyncMock())
        bot.pool = mock_pool
        bot.db_pool = MagicMock()

        mock_http = MagicMock()
        mock_http.bulk_upsert_global_commands = AsyncMock()
        mock_http.bulk_upsert_guild_commands = AsyncMock()
        mock_conn = MagicMock(http=mock_http)
        caplog.set_level(logging.WARNING, logger="bot.client")
        with (
            patch.object(discord.Client, "user", PropertyMock(return_value=MagicMock(id=123))),
            patch.object(discord.Client, "guilds", PropertyMock(return_value=[])),
            patch.object(bot, "_register_server", new_callable=AsyncMock),
            patch.object(bot, "_connection", mock_conn),
            patch.object(bot.tree, "copy_global_to"),
            patch.object(bot.tree, "sync", new_callable=AsyncMock),
            patch(
                "bot.commands.music.reconnect_music_voice_after_ready",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            await bot.on_ready()

        assert "Music voice recovery failed" in caplog.text

    @pytest.mark.asyncio
    async def test_on_ready_lavalink_connection_failure(self, mock_settings, caplog):
        from bot.client import FFOBot

        mock_settings.feature_music = True
        mock_settings.lavalink_host = "127.0.0.1"
        mock_settings.lavalink_port = 2333
        mock_settings.lavalink_password = "secret"
        bot = FFOBot(mock_settings)
        mock_pool = MagicMock()
        mock_pool.create_node = AsyncMock(side_effect=ConnectionError("Connection refused"))
        bot.pool = mock_pool
        caplog.set_level(logging.WARNING, logger="bot.client")

        mock_http = MagicMock()
        mock_http.bulk_upsert_global_commands = AsyncMock()
        mock_http.bulk_upsert_guild_commands = AsyncMock()
        mock_conn = MagicMock(http=mock_http)
        with (
            patch.object(discord.Client, "user", PropertyMock(return_value=MagicMock(id=123))),
            patch.object(discord.Client, "guilds", PropertyMock(return_value=[])),
            patch.object(bot, "_register_server", new_callable=AsyncMock),
            patch.object(bot, "_connection", mock_conn),
            patch.object(bot.tree, "copy_global_to"),
            patch.object(bot.tree, "sync", new_callable=AsyncMock),
        ):
            await bot.on_ready()

        assert bot.pool is None
        assert "Lavalink connection failed" in caplog.text
