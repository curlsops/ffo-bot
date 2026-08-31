from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.cooldown import CommandCooldown, with_cooldown


def make_cooldown(**overrides):
    defaults = {"rate": 1, "per": 60.0}
    defaults.update(overrides)
    return CommandCooldown(**defaults)


@pytest.mark.parametrize("per,expected_interval", [(1.0, 60.0), (60.0, 60.0), (300.0, 300.0)])
def test_init_stores_per_and_prune_interval(per, expected_interval):
    cooldown = make_cooldown(per=per)
    assert cooldown.rate == 1
    assert cooldown.per == per
    assert cooldown._prune_interval_seconds == expected_interval


@pytest.mark.parametrize("user_id", [0, 1, 999, 123456789])
@pytest.mark.parametrize("guild_id", [0, 1, 999])
@pytest.mark.asyncio
async def test_first_check_allowed(user_id, guild_id):
    cooldown = make_cooldown()
    allowed, retry = await cooldown.check(user_id, guild_id, "cmd")
    assert allowed is True
    assert retry == 0.0


@pytest.mark.parametrize("rate", [1, 2, 3, 5, 10])
@pytest.mark.asyncio
async def test_exactly_rate_allowed_then_blocked(rate):
    cooldown = make_cooldown(rate=rate)
    for _ in range(rate):
        allowed, _ = await cooldown.check(1, 1, "ping")
        assert allowed is True
    allowed, retry = await cooldown.check(1, 1, "ping")
    assert allowed is False
    assert retry > 0


@pytest.mark.parametrize("n_users", [2, 3, 5])
@pytest.mark.asyncio
async def test_users_are_independent(n_users):
    cooldown = make_cooldown(rate=1)
    for uid in range(n_users):
        allowed, _ = await cooldown.check(uid, 1, "cmd")
        assert allowed is True
    for uid in range(n_users):
        allowed, _ = await cooldown.check(uid, 1, "cmd")
        assert allowed is False


@pytest.mark.parametrize("n_guilds", [2, 3, 5])
@pytest.mark.asyncio
async def test_guilds_are_independent(n_guilds):
    cooldown = make_cooldown(rate=1)
    for gid in range(n_guilds):
        allowed, _ = await cooldown.check(1, gid, "cmd")
        assert allowed is True
    for gid in range(n_guilds):
        allowed, _ = await cooldown.check(1, gid, "cmd")
        assert allowed is False


@pytest.mark.parametrize("command_name", ["ping", "help", "admin_config", "a", "x_y_z"])
@pytest.mark.asyncio
async def test_command_name_is_isolated(command_name):
    cooldown = make_cooldown(rate=1)
    allowed, _ = await cooldown.check(1, 1, command_name)
    assert allowed is True
    allowed, _ = await cooldown.check(1, 1, command_name)
    assert allowed is False


@pytest.mark.asyncio
async def test_different_commands_are_independent():
    cooldown = make_cooldown(rate=1)
    await cooldown.check(1, 1, "cmd_a")
    allowed, _ = await cooldown.check(1, 1, "cmd_b")
    assert allowed is True


@pytest.mark.asyncio
async def test_guild_id_none_maps_to_zero_bucket():
    cooldown = make_cooldown(rate=1)
    allowed, _ = await cooldown.check(1, None, "cmd")
    assert allowed is True
    allowed, _ = await cooldown.check(1, 0, "cmd")
    assert allowed is False


@pytest.mark.asyncio
async def test_with_cooldown_skips_when_no_command():
    with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
        check = with_cooldown(rate=1, per=60.0)
    interaction = MagicMock()
    interaction.guild_id = 123
    interaction.command = None
    assert await check(interaction) is True


@pytest.mark.parametrize("guild_id", [None, 0])
@pytest.mark.asyncio
async def test_with_cooldown_skips_when_no_guild(guild_id):
    with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
        check = with_cooldown(rate=1, per=60.0)
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.command = MagicMock(qualified_name="test")
    assert await check(interaction) is True


@pytest.mark.asyncio
async def test_with_cooldown_blocks_second_attempt_and_sends_ephemeral_message():
    with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
        check = with_cooldown(rate=1, per=60.0)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user = MagicMock(id=1)
    interaction.command = MagicMock(qualified_name="x")
    interaction.response.send_message = AsyncMock()
    assert await check(interaction) is True
    assert await check(interaction) is False
    interaction.response.send_message.assert_awaited_once()
    call = interaction.response.send_message.call_args
    content = call.kwargs.get("content") or (call.args[0] if call.args else "")
    assert "Cooldown" in str(content)
    assert call.kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_prunes_stale_keys_periodically():
    now = datetime.now(UTC)
    with patch("bot.utils.cooldown.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.UTC = UTC
        cooldown = make_cooldown(rate=1, per=60.0)
        await cooldown.check(1, 1, "a")
        await cooldown.check(2, 2, "b")
        assert set(cooldown._buckets) == {(1, 1, "a"), (2, 2, "b")}

        mock_dt.now.return_value = now + timedelta(seconds=61)
        allowed, retry = await cooldown.check(3, 3, "c")
        assert allowed is True
        assert retry == 0.0
        assert set(cooldown._buckets) == {(3, 3, "c")}


@pytest.mark.asyncio
async def test_prune_keeps_non_stale_key():
    now = datetime.now(UTC)
    with patch("bot.utils.cooldown.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.UTC = UTC
        cooldown = make_cooldown(rate=2, per=60.0)
        await cooldown.check(1, 1, "same")

        mock_dt.now.return_value = now + timedelta(seconds=61)
        allowed, retry = await cooldown.check(1, 1, "same")
        assert allowed is True
        assert retry == 0.0
        assert (1, 1, "same") in cooldown._buckets


@pytest.mark.asyncio
async def test_prune_handles_mixed_stale_and_non_stale_keys():
    now = datetime.now(UTC)
    with patch("bot.utils.cooldown.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.UTC = UTC
        cooldown = make_cooldown(rate=2, per=60.0)
        await cooldown.check(1, 1, "mixed")
        await cooldown.check(2, 2, "stale")
        cooldown._buckets[(1, 1, "mixed")] = [now + timedelta(seconds=30)]

        mock_dt.now.return_value = now + timedelta(seconds=61)
        allowed, retry = await cooldown.check(3, 3, "new")
        assert allowed is True
        assert retry == 0.0
        assert (1, 1, "mixed") in cooldown._buckets
        assert (2, 2, "stale") not in cooldown._buckets
