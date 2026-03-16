from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


class TestFFOBotHealthServer:
    @pytest.mark.asyncio
    async def test_start_health_server(self, bot, mock_settings):
        with patch("bot.client.HealthCheckServer") as mock_cls:
            mock_server = MagicMock(start=AsyncMock(), runner=MagicMock())
            mock_cls.return_value = mock_server

            await bot._start_health_server()

            mock_cls.assert_called_once_with(
                bot,
                port=mock_settings.health_check_port,
                public_key=None,
                host=mock_settings.health_check_host,
            )
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
    @staticmethod
    def make_interaction(guild_id=123, done=False, command="test"):
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
