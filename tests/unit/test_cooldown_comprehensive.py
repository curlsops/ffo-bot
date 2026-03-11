from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.cooldown import CommandCooldown, with_cooldown


class TestCommandCooldownParametrized:
    @pytest.mark.parametrize("user_id", [0, 1, 999, 123456789])
    @pytest.mark.parametrize("guild_id", [0, 1, 999])
    @pytest.mark.asyncio
    async def test_first_check_allowed(self, user_id, guild_id):
        c = CommandCooldown(rate=1, per=60.0)
        allowed, retry = await c.check(user_id, guild_id, "cmd")
        assert allowed
        assert retry == 0.0

    @pytest.mark.parametrize("rate", [1, 2, 3, 5, 10])
    @pytest.mark.asyncio
    async def test_exactly_rate_allowed(self, rate):
        c = CommandCooldown(rate=rate, per=60.0)
        for _ in range(rate):
            allowed, _ = await c.check(1, 1, "x")
            assert allowed
        allowed, retry = await c.check(1, 1, "x")
        assert not allowed
        assert retry > 0

    @pytest.mark.parametrize("per", [1.0, 10.0, 60.0, 300.0])
    @pytest.mark.asyncio
    async def test_per_stored(self, per):
        c = CommandCooldown(rate=1, per=per)
        assert c.per == per
        assert c.rate == 1

    @pytest.mark.parametrize("cmd", ["ping", "help", "admin_config", "a", "x_y_z"])
    @pytest.mark.asyncio
    async def test_command_name_isolated(self, cmd):
        c = CommandCooldown(rate=1, per=60.0)
        allowed, _ = await c.check(1, 1, cmd)
        assert allowed
        allowed, _ = await c.check(1, 1, cmd)
        assert not allowed

    @pytest.mark.parametrize("n_users", [2, 3, 5])
    @pytest.mark.asyncio
    async def test_users_independent(self, n_users):
        c = CommandCooldown(rate=1, per=60.0)
        for uid in range(n_users):
            allowed, _ = await c.check(uid, 1, "cmd")
            assert allowed
        for uid in range(n_users):
            allowed, _ = await c.check(uid, 1, "cmd")
            assert not allowed

    @pytest.mark.parametrize("n_guilds", [2, 3, 5])
    @pytest.mark.asyncio
    async def test_guilds_independent(self, n_guilds):
        c = CommandCooldown(rate=1, per=60.0)
        for gid in range(n_guilds):
            allowed, _ = await c.check(1, gid, "cmd")
            assert allowed
        for gid in range(n_guilds):
            allowed, _ = await c.check(1, gid, "cmd")
            assert not allowed

    @pytest.mark.asyncio
    async def test_guild_id_zero_used_as_key(self):
        c = CommandCooldown(rate=1, per=60.0)
        allowed, _ = await c.check(1, 0, "cmd")
        assert allowed
        allowed, _ = await c.check(1, 0, "cmd")
        assert not allowed

    @pytest.mark.asyncio
    async def test_different_commands_independent(self):
        c = CommandCooldown(rate=1, per=60.0)
        await c.check(1, 1, "cmd_a")
        allowed, _ = await c.check(1, 1, "cmd_b")
        assert allowed


class TestWithCooldownParametrized:
    @pytest.mark.parametrize("guild_id", [None, 0])
    @pytest.mark.asyncio
    async def test_skips_when_no_guild(self, guild_id):
        with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
            check = with_cooldown(rate=1, per=60.0)
        i = MagicMock()
        i.guild_id = guild_id
        i.command = MagicMock(qualified_name="test")
        result = await check(i)
        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_second_and_sends_ephemeral(self):
        with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
            check = with_cooldown(rate=1, per=60.0)
        i = MagicMock()
        i.guild_id = 1
        i.user = MagicMock(id=1)
        i.command = MagicMock(qualified_name="x")
        i.response.send_message = AsyncMock()
        assert await check(i) is True
        assert await check(i) is False
        i.response.send_message.assert_awaited_once()
        call = i.response.send_message.call_args
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")
        assert "Cooldown" in str(content)
        assert call.kwargs.get("ephemeral") is True
