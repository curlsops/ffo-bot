"""Minecraft RCON client for whitelist management.

Implements RCON protocol directly using sockets with timeout support,
avoiding signal-based timeouts that don't work in thread pools.
"""

import asyncio
import logging
import re
import socket
import struct

from config.settings import Settings

logger = logging.getLogger(__name__)

RCON_PACKET_LOGIN = 3
RCON_PACKET_COMMAND = 2
RCON_PACKET_RESPONSE = 0


class MinecraftRCONError(Exception):
    """Raised when RCON command fails."""

    pass


def _send_rcon_packet(sock: socket.socket, packet_type: int, payload: str, req_id: int) -> None:
    data = payload.encode("utf-8") + b"\x00\x00"
    packet = struct.pack("<iii", len(data) + 8, req_id, packet_type) + data
    sock.sendall(packet)


def _recv_rcon_packet(sock: socket.socket) -> tuple[int, int, str]:
    header = sock.recv(12)
    if len(header) < 12:
        raise MinecraftRCONError("Connection closed or incomplete header")
    length, req_id, packet_type = struct.unpack("<iii", header)
    body_len = length - 8
    body = b""
    while len(body) < body_len:
        chunk = sock.recv(body_len - len(body))
        if not chunk:
            break
        body += chunk
    response = body.rstrip(b"\x00").decode("utf-8", errors="replace")
    return req_id, packet_type, response


def _rcon_command(host: str, port: int, password: str, command: str, timeout: float = 10.0) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        _send_rcon_packet(sock, RCON_PACKET_LOGIN, password, 1)
        req_id, _, _ = _recv_rcon_packet(sock)
        if req_id == -1:
            raise MinecraftRCONError("RCON authentication failed")
        _send_rcon_packet(sock, RCON_PACKET_COMMAND, command, 2)
        _, _, response = _recv_rcon_packet(sock)
        return response
    finally:
        sock.close()


class MinecraftRCONClient:
    """Async wrapper for Minecraft RCON commands using socket-based implementation."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def _is_configured(self) -> bool:
        return bool(
            self._settings.feature_minecraft_whitelist
            and self._settings.minecraft_rcon_host
            and self._settings.minecraft_rcon_password
        )

    async def _run_rcon(self, command: str) -> str:
        if not self._is_configured():
            raise MinecraftRCONError("Minecraft RCON not configured")

        def _sync_command() -> str:
            return _rcon_command(
                self._settings.minecraft_rcon_host,
                self._settings.minecraft_rcon_port,
                self._settings.minecraft_rcon_password,
                command,
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_command)

    async def whitelist_add(self, username: str) -> str:
        return await self._run_rcon(f"whitelist add {username}")

    async def whitelist_remove(self, username: str) -> str:
        return await self._run_rcon(f"whitelist remove {username}")

    async def whitelist_list(self) -> str:
        return await self._run_rcon("whitelist list")


def parse_whitelist_list_response(response: str) -> list[str]:
    """Parse Minecraft whitelist list output into usernames.

    Handles: "There are N whitelisted players: a, b, c"
    or "There is 1 whitelisted player: a" or "There are 0 whitelisted players: "
    """
    response = response.strip()
    m = re.search(r":\s*(.+)$", response, re.DOTALL)
    if not m:
        return []
    names_str = m.group(1).strip()
    if not names_str:
        return []  # pragma: no cover - unreachable: strip() removes trailing ws before regex
    parts = names_str.split(",")
    result = []
    for p in parts:
        s = p.strip()
        if s:
            result.append(s)
    return result
