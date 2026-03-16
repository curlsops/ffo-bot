import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers import db_pool_with_conn


class TestFFOBotGuildEvents:
    @pytest.mark.asyncio
    async def test_register_server(self, bot):
        conn = AsyncMock()
        bot.db_pool = db_pool_with_conn(conn)
        guild = MagicMock(id=123456789, name="Test Server")

        await bot._register_server(guild)
        conn.execute.assert_called_once()
        assert guild.id in conn.execute.call_args[0]
        assert guild.name in conn.execute.call_args[0]

    @pytest.mark.asyncio
    async def test_register_server_handles_error(self, bot, caplog):
        caplog.set_level(logging.WARNING, logger="bot.client")
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=Exception("Database error"))
        bot.db_pool = db_pool_with_conn(conn)

        await bot._register_server(MagicMock(id=123456789, name="Test"))
        assert "Failed to register server 123456789" in caplog.text

    @pytest.mark.asyncio
    async def test_register_server_returns_when_db_pool_none(self, bot):
        bot.db_pool = None
        guild = MagicMock(id=1, name="Test")
        await bot._register_server(guild)

    @pytest.mark.asyncio
    async def test_on_guild_join_skips_owner_notify_when_not_configured(self, bot):
        bot.metrics = MagicMock()
        bot.settings.bot_owner_server_id = None
        bot.settings.bot_owner_notify_channel_id = None
        guild = MagicMock(id=123, name="New")
        with patch.object(bot, "_register_server", new_callable=AsyncMock):
            with patch.object(bot.tree, "copy_global_to"):
                with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                    with patch.object(bot, "get_channel") as mock_get_channel:
                        await bot.on_guild_join(guild)
        mock_get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_guild_join(self, bot):
        bot.metrics = MagicMock()
        guild = MagicMock(id=123, name="New")
        with patch.object(bot, "_register_server", new_callable=AsyncMock) as mock_reg:
            with patch.object(bot.tree, "copy_global_to") as mock_copy:
                with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                    await bot.on_guild_join(guild)
                    mock_reg.assert_called_once_with(guild)
                    mock_copy.assert_called_once_with(guild=guild)
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
        bot.metrics = None
        with patch.object(bot, "_register_server", new_callable=AsyncMock):
            with patch.object(bot.tree, "copy_global_to"):
                with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                    await bot.on_guild_join(MagicMock(id=123, name="New"))
        await bot.on_guild_remove(MagicMock(id=123, name="Removed"))

    @pytest.mark.asyncio
    async def test_on_guild_join_notifies_owner_when_configured(self, bot):
        bot.metrics = MagicMock()
        bot.settings.bot_owner_server_id = 999
        bot.settings.bot_owner_notify_channel_id = 888
        guild = MagicMock(id=123, name="NewServer", member_count=50)
        owner_ch = MagicMock()
        owner_ch.guild = MagicMock(id=999)
        owner_ch.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=owner_ch)

        with patch.object(bot, "_register_server", new_callable=AsyncMock):
            with patch.object(bot.tree, "copy_global_to"):
                with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                    await bot.on_guild_join(guild)

        owner_ch.send.assert_awaited_once()
        embed = owner_ch.send.call_args[1]["embed"]
        assert embed.title == "Bot Added to Server"
        assert "NewServer" in embed.description
        assert str(123) in str(embed.fields)

    @pytest.mark.asyncio
    async def test_on_guild_join_owner_notify_send_failure_logs_warning(self, bot, caplog):
        bot.metrics = MagicMock()
        bot.settings.bot_owner_server_id = 999
        bot.settings.bot_owner_notify_channel_id = 888
        guild = MagicMock(id=123, name="NewServer", member_count=50)
        owner_ch = MagicMock()
        owner_ch.guild = MagicMock(id=999)
        owner_ch.send = AsyncMock(side_effect=Exception("send failed"))
        bot.get_channel = MagicMock(return_value=owner_ch)
        caplog.set_level(logging.WARNING, logger="bot.client")

        with patch.object(bot, "_register_server", new_callable=AsyncMock):
            with patch.object(bot.tree, "copy_global_to"):
                with patch.object(bot.tree, "sync", new_callable=AsyncMock):
                    await bot.on_guild_join(guild)

        assert "Failed to notify owner" in caplog.text
