import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands


class CommandCooldown:
    def __init__(self, rate: int = 1, per: float = 60.0):
        self.rate = rate
        self.per = per
        self._buckets: dict[tuple[int, int, str], list[datetime]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._prune_interval_seconds = max(60.0, per)
        self._next_prune_at = datetime.now(UTC) + timedelta(seconds=self._prune_interval_seconds)

    async def check(self, user_id: int, guild_id: int, command_name: str) -> tuple[bool, float]:
        key = (user_id, guild_id or 0, command_name)
        async with self._lock:
            now = datetime.now(UTC)
            self._maybe_prune_stale_buckets(now)
            self._buckets[key] = [
                t for t in self._buckets[key] if (now - t).total_seconds() < self.per
            ]
            if len(self._buckets[key]) >= self.rate:
                oldest = min(self._buckets[key])
                retry_after = self.per - (now - oldest).total_seconds()
                return False, max(0.0, retry_after)
            self._buckets[key].append(now)
            return True, 0.0

    def _maybe_prune_stale_buckets(self, now: datetime) -> None:
        if now < self._next_prune_at:
            return
        stale_keys: list[tuple[int, int, str]] = []
        for key, timestamps in self._buckets.items():
            self._buckets[key] = [t for t in timestamps if (now - t).total_seconds() < self.per]
            if not self._buckets[key]:
                stale_keys.append(key)
        for key in stale_keys:
            del self._buckets[key]
        self._next_prune_at = now + timedelta(seconds=self._prune_interval_seconds)


def with_cooldown(rate: int = 1, per: float = 60.0):
    cooldown = CommandCooldown(rate=rate, per=per)

    async def check(interaction: discord.Interaction) -> bool:
        if not interaction.guild_id or not interaction.command:
            return True
        allowed, retry = await cooldown.check(
            interaction.user.id, interaction.guild_id, interaction.command.qualified_name
        )
        if not allowed:
            await interaction.response.send_message(
                f"Cooldown: try again in {retry:.0f}s.", ephemeral=True
            )
            return False
        return True

    return app_commands.check(check)
