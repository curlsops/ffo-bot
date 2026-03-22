import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.minecraft_rcon import (
    RCON_PACKET_COMMAND,
    RCON_PACKET_LOGIN,
    MinecraftRCONClient,
    MinecraftRCONError,
    RconTarget,
    _rcon_command,
    _recv_rcon_packet,
    _send_rcon_packet,
    parse_whitelist_list_response,
)


class TestRconPacketFunctions:
    def test_send_rcon_packet(self):
        mock_sock = MagicMock()
        _send_rcon_packet(mock_sock, RCON_PACKET_LOGIN, "password", 1)
        mock_sock.sendall.assert_called_once()
        packet = mock_sock.sendall.call_args[0][0]
        length, req_id, packet_type = struct.unpack("<iii", packet[:12])
        assert req_id == 1
        assert packet_type == RCON_PACKET_LOGIN
        assert b"password" in packet

    def test_recv_rcon_packet_success(self):
        payload = b"response\x00\x00"
        header = struct.pack("<iii", len(payload) + 8, 1, 0)
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [header, payload]
        req_id, ptype, response = _recv_rcon_packet(mock_sock)
        assert req_id == 1
        assert ptype == 0
        assert response == "response"

    def test_recv_rcon_packet_incomplete_header(self):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"\x00" * 5
        with pytest.raises(MinecraftRCONError, match="incomplete header"):
            _recv_rcon_packet(mock_sock)

    def test_recv_rcon_packet_body_connection_closed(self):
        header = struct.pack("<iii", 20, 1, 0)
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [header, b"partial", b""]
        req_id, ptype, response = _recv_rcon_packet(mock_sock)
        assert req_id == 1
        assert response == "partial"

    def test_rcon_command_auth_failed(self):
        with patch("bot.services.minecraft_rcon.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            auth_header = struct.pack("<iii", 10, -1, 0)
            auth_body = b"\x00\x00"
            mock_sock.recv.side_effect = [auth_header, auth_body]
            with pytest.raises(MinecraftRCONError, match="authentication failed"):
                _rcon_command("localhost", 25575, "wrong", "test")

    def test_rcon_command_success(self):
        with patch("bot.services.minecraft_rcon.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            auth_header = struct.pack("<iii", 10, 1, 0)
            auth_body = b"\x00\x00"
            cmd_header = struct.pack("<iii", 24, 2, 0)
            cmd_body = b"command result\x00\x00"
            mock_sock.recv.side_effect = [auth_header, auth_body, cmd_header, cmd_body]
            result = _rcon_command("localhost", 25575, "secret", "test cmd")
            assert result == "command result"
            mock_sock.close.assert_called_once()


class TestParseWhitelistListResponse:
    def test_multiple_players(self):
        assert parse_whitelist_list_response(
            "There are 3 whitelisted players: Alice, Bob, Charlie"
        ) == ["Alice", "Bob", "Charlie"]

    def test_single_player(self):
        assert parse_whitelist_list_response("There is 1 whitelisted player: Steve") == ["Steve"]

    def test_zero_players(self):
        assert parse_whitelist_list_response("There are 0 whitelisted players: ") == []

    def test_empty_after_colon(self):
        assert parse_whitelist_list_response("Some text: ") == []

    def test_whitespace_only_after_colon_returns_empty(self):
        assert parse_whitelist_list_response("Some text: ") == []

    def test_no_colon_returns_empty(self):
        assert parse_whitelist_list_response("No colon here") == []

    def test_strips_whitespace(self):
        assert parse_whitelist_list_response("There are 2 whitelisted players:  a ,  b  ") == [
            "a",
            "b",
        ]

    def test_filters_empty_parts(self):
        assert parse_whitelist_list_response("There are 3 whitelisted players: a, , b") == [
            "a",
            "b",
        ]

    def test_trailing_comma_and_whitespace_only_part(self):
        assert parse_whitelist_list_response("There are 2 whitelisted players: x,   ") == ["x"]


class TestMinecraftRCONClient:
    @pytest.fixture
    def configured_settings(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = None
        s.minecraft_rcon_host = "localhost"
        s.minecraft_rcon_port = 25575
        s.minecraft_rcon_password = "secret"
        return s

    @pytest.fixture
    def unconfigured_settings(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = False
        s.minecraft_rcon_targets = None
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
        with patch.object(
            client, "_run_rcon_on", new_callable=AsyncMock, return_value="Added Steve"
        ) as mock_run:
            result = await client.whitelist_add("Steve")
            mock_run.assert_awaited_once()
            assert mock_run.await_args[0][1] == "whitelist add Steve"
            assert result == "default: Added Steve"

    @pytest.mark.asyncio
    async def test_whitelist_remove_success(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(
            client, "_run_rcon_on", new_callable=AsyncMock, return_value="Removed Steve"
        ) as mock_run:
            result = await client.whitelist_remove("Steve")
            mock_run.assert_awaited_once()
            assert mock_run.await_args[0][1] == "whitelist remove Steve"
            assert result == "default: Removed Steve"

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
    async def test_whitelist_on_success(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(
            client,
            "_run_rcon_on",
            new_callable=AsyncMock,
            return_value="Whitelist is now turned on",
        ) as mock_run:
            result = await client.whitelist_on()
            mock_run.assert_awaited_once()
            assert mock_run.await_args[0][1] == "whitelist on"
            assert result == "default: Whitelist is now turned on"

    @pytest.mark.asyncio
    async def test_whitelist_off_success(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(
            client,
            "_run_rcon_on",
            new_callable=AsyncMock,
            return_value="Whitelist is now turned off",
        ) as mock_run:
            result = await client.whitelist_off()
            mock_run.assert_awaited_once()
            assert mock_run.await_args[0][1] == "whitelist off"
            assert result == "default: Whitelist is now turned off"

    @pytest.mark.asyncio
    async def test_run_rcon_raises_when_no_targets(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        client._targets = []
        with pytest.raises(MinecraftRCONError, match="not configured"):
            await client._run_rcon("whitelist list")

    @pytest.mark.asyncio
    async def test_run_rcon_on_raises_when_not_configured(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        client._targets = []
        t = RconTarget(id="x", host="h", port=25575, password="p")
        with pytest.raises(MinecraftRCONError, match="not configured"):
            await client._run_rcon_on(t, "whitelist list")

    @pytest.mark.asyncio
    async def test_run_rcon_executes_in_executor(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)

        with patch("bot.services.minecraft_rcon._rcon_command", return_value="ok") as mock_cmd:
            result = await client._run_rcon("whitelist list")

        assert result == "ok"
        mock_cmd.assert_called_once_with("localhost", 25575, "secret", "whitelist list")

    def test_targets_json_skips_non_dict_entries(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = '[null, 1, {"id":"a","host":"h1","port":25575,"password":"p1"}]'
        s.minecraft_rcon_host = "ignored"
        s.minecraft_rcon_port = 25575
        s.minecraft_rcon_password = "ignored"
        client = MinecraftRCONClient(s)
        assert len(client._targets) == 1
        assert client._targets[0].id == "a"

    def test_targets_json_skips_dict_without_host_or_password(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = '[{"id":"onlyhost","host":"h1"},{"id":"onlypw","password":"p"}]'
        s.minecraft_rcon_host = "localhost"
        s.minecraft_rcon_port = 25575
        s.minecraft_rcon_password = "secret"
        client = MinecraftRCONClient(s)
        assert len(client._targets) == 1
        assert client._targets[0].id == "default"

    def test_targets_from_json_array(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = (
            '[{"id":"alpha","host":"h1","port":25575,"password":"p1"},'
            '{"id":"beta","host":"h2","port":25576,"password":"p2"}]'
        )
        s.minecraft_rcon_host = "ignored"
        s.minecraft_rcon_port = 25575
        s.minecraft_rcon_password = "ignored"
        client = MinecraftRCONClient(s)
        assert len(client._targets) == 2
        assert client._targets[0].id == "alpha"
        assert client._targets[1].host == "h2"

    def test_invalid_json_falls_back_to_legacy(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = "not-json{"
        s.minecraft_rcon_host = "localhost"
        s.minecraft_rcon_port = 25575
        s.minecraft_rcon_password = "secret"
        client = MinecraftRCONClient(s)
        assert len(client._targets) == 1
        assert client._targets[0].id == "default"

    def test_empty_json_array_falls_back_to_legacy(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = "[]"
        s.minecraft_rcon_host = "localhost"
        s.minecraft_rcon_port = 25575
        s.minecraft_rcon_password = "secret"
        client = MinecraftRCONClient(s)
        assert len(client._targets) == 1

    @pytest.mark.asyncio
    async def test_whitelist_add_broadcast_partial_failure(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = (
            '[{"id":"a","host":"h1","port":25575,"password":"p1"},'
            '{"id":"b","host":"h2","port":25575,"password":"p2"}]'
        )
        client = MinecraftRCONClient(s)
        with patch.object(client, "_run_rcon_on", new_callable=AsyncMock) as m:
            m.side_effect = ["ok", MinecraftRCONError("down")]
            result = await client.whitelist_add("Steve")
        assert "a: ok" in result
        assert "b: failed" in result

    @pytest.mark.asyncio
    async def test_whitelist_add_all_targets_fail_raises(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = (
            '[{"id":"a","host":"h1","port":25575,"password":"p1"},'
            '{"id":"b","host":"h2","port":25575,"password":"p2"}]'
        )
        client = MinecraftRCONClient(s)
        with patch.object(client, "_run_rcon_on", new_callable=AsyncMock) as m:
            m.side_effect = MinecraftRCONError("down")
            with pytest.raises(MinecraftRCONError, match="All targets failed"):
                await client.whitelist_add("Steve")

    @pytest.mark.asyncio
    async def test_push_master_adds_and_removes(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(client, "_run_rcon_on", new_callable=AsyncMock) as m:
            m.side_effect = [
                "There are 1 whitelisted players: OldName",
                "Removed OldName",
                "Added Steve",
            ]
            results = await client.push_master_whitelist(["Steve"])
        assert len(results) == 1
        assert results[0].added == ["Steve"]
        assert results[0].removed == ["OldName"]
        assert results[0].error is None

    @pytest.mark.asyncio
    async def test_push_master_list_fails_records_error(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(client, "_run_rcon_on", new_callable=AsyncMock) as m:
            m.side_effect = MinecraftRCONError("no connection")
            results = await client.push_master_whitelist(["Steve"])
        assert len(results) == 1
        assert results[0].error == "no connection"

    @pytest.mark.asyncio
    async def test_push_master_case_insensitive(self, configured_settings):
        client = MinecraftRCONClient(configured_settings)
        with patch.object(client, "_run_rcon_on", new_callable=AsyncMock) as m:
            m.side_effect = [
                "There are 1 whitelisted players: steve",
            ]
            results = await client.push_master_whitelist(["Steve"])
        assert results[0].added == []
        assert results[0].removed == []

    @pytest.mark.asyncio
    async def test_push_master_not_configured(self, unconfigured_settings):
        client = MinecraftRCONClient(unconfigured_settings)
        with pytest.raises(MinecraftRCONError, match="not configured"):
            await client.push_master_whitelist(["Steve"])

    def test_targets_json_uses_name_as_id_and_auto_id(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = (
            '[{"name":"named","host":"h0","port":25575,"password":"p0"},'
            '{"host":"h1","port":25575,"password":"p1"}]'
        )
        s.minecraft_rcon_host = "ignored"
        client = MinecraftRCONClient(s)
        assert len(client._targets) == 2
        assert client._targets[0].id == "named"
        assert client._targets[1].id == "server1"

    def test_legacy_empty_when_no_host(self):
        s = MagicMock()
        s.feature_minecraft_whitelist = True
        s.minecraft_rcon_targets = None
        s.minecraft_rcon_host = None
        s.minecraft_rcon_password = None
        assert len(MinecraftRCONClient(s)._targets) == 0
