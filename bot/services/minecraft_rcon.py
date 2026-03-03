"""Minecraft RCON client for whitelist management.

Uses mcrcon to send commands to a Minecraft server. Runs sync RCON in a thread
pool to avoid blocking the event loop.
"""

import asyncio
import logging
import re

from config.settings import Settings

logger = logging.getLogger(__name__)


class MinecraftRCONError(Exception):
    """Raised when RCON command fails."""

    pass


class MinecraftRCONClient:
    """Async wrapper around mcrcon for Minecraft server commands."""

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
            from mcrcon import MCRcon

            with MCRcon(
                self._settings.minecraft_rcon_host,
                self._settings.minecraft_rcon_password,
                port=self._settings.minecraft_rcon_port,
            ) as mcr:
                return mcr.command(command)

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
