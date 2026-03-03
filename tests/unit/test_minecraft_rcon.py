"""Tests for Minecraft RCON client."""

from unittest.mock import MagicMock, patch

import pytest

from bot.services.minecraft_rcon import (
    MinecraftRCONClient,
    MinecraftRCONError,
    parse_whitelist_list_response,
)


class TestParseWhitelistListResponse:
    def test_multiple_players(self):
        assert parse_whitelist_list_response(
            "There are 3 whitelisted players: Alice, Bob, Charlie"
        ) == ["Alice", "Bob", "Charlie"]

    def test_single_player(self):
        assert parse_whitelist_list_response(
            "There is 1 whitelisted player: Steve"
        ) == ["Steve"]

    def test_zero_players(self):
        assert parse_whitelist_list_response(
            "There are 0 whitelisted players: "
        ) == []

    def test_empty_after_colon(self):
        assert parse_whitelist_list_response("Some text: ") == []

    def test_whitespace_only_after_colon_returns_empty(self):
        assert parse_whitelist_list_response("Some text: ") == []

    def test_no_colon_returns_empty(self):
        assert parse_whitelist_list_response("No colon here") == []

    def test_strips_whitespace(self):
        assert parse_whitelist_list_response(
            "There are 2 whitelisted players:  a ,  b  "
        ) == ["a", "b"]

    def test_filters_empty_parts(self):
        assert parse_whitelist_list_response(
            "There are 3 whitelisted players: a, , b"
        ) == ["a", "b"]

    def test_trailing_comma_and_whitespace_only_part(self):
        assert parse_whitelist_list_response(
            "There are 2 whitelisted players: x,   "
        ) == ["x"]


class TestMinecraftRCONClient:
    @pytest.fixture
    def configured_settings(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_host = "localhost"
        s.minecraft_rcon_port = 25575
        s.minecraft_rcon_password = "secret"
        return s

    @pytest.fixture
    def unconfigured_settings(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = False
        s.minecraft_rcon_host = None
        s.minecraft_rcon_password = None
        return s

    @pytest.mark.asyncio
    async def test_whitelist_add_not_configured_raises(self, unconfigured_settings):
        client = MinecraftRCONClient(unconfigured_settings)
        with pytest.raises(MinecraftRCONError, match="not configured"):
            await client.whitelist_add("Steve")

    @pytest.mark.asyncio
    async def test_whitelist_add_success(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(client, "_run_rcon", return_value="Added Steve") as mock_run:
            result = await client.whitelist_add("Steve")
            mock_run.assert_called_once_with("whitelist add Steve")
            assert result == "Added Steve"

    @pytest.mark.asyncio
    async def test_whitelist_remove_success(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(client, "_run_rcon", return_value="Removed Steve") as mock_run:
            result = await client.whitelist_remove("Steve")
            mock_run.assert_called_once_with("whitelist remove Steve")
            assert result == "Removed Steve"

    @pytest.mark.asyncio
    async def test_whitelist_list_success(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(
            client,
            "_run_rcon",
            return_value="There are 2 whitelisted players: Alice, Bob",
        ) as mock_run:
            result = await client.whitelist_list()
            mock_run.assert_called_once_with("whitelist list")
            assert "Alice" in result

    @pytest.mark.asyncio
    async def test_run_rcon_executes_in_executor(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)

        async def run_callback(executor, func):
            return func()

        with patch("bot.services.minecraft_rcon.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = run_callback

            with patch("mcrcon.MCRcon") as mock_mcr:
                mock_mcr.return_value.__enter__.return_value.command.return_value = "ok"
                result = await client._run_rcon("whitelist list")

            assert result == "ok"
            mock_mcr.assert_called_once_with(
                "localhost", "secret", port=25575
            )
