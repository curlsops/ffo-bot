from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.auth.command_helpers import (
    _get_interaction,
    execute_command,
    require_admin,
    require_guild,
    require_mod,
    require_rcon,
    require_super_admin,
    send_error,
)


@pytest.mark.asyncio
async def test_send_error_adds_prefix():
    i = MagicMock()
    i.followup.send = AsyncMock()
    await send_error(i, "Invalid user.")
    i.followup.send.assert_awaited_once_with("❌ Invalid user.", ephemeral=True)


@pytest.mark.asyncio
async def test_send_error_preserves_existing_prefix():
    i = MagicMock()
    i.followup.send = AsyncMock()
    await send_error(i, "❌ Server only.")
    i.followup.send.assert_awaited_once_with("❌ Server only.", ephemeral=True)


def _mock_interaction(guild_id=None):
    i = MagicMock(guild_id=guild_id, user=MagicMock(id=1))
    i.followup.send = AsyncMock()
    return i


@pytest.mark.asyncio
async def test_require_admin_no_guild_returns_false():
    i = _mock_interaction(guild_id=None)
    bot = MagicMock()
    assert await require_admin(i, "cmd", bot) is False
    i.followup.send.assert_not_called()


@pytest.mark.asyncio
async def test_require_admin_granted_returns_true():
    i = _mock_interaction(guild_id=1)
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    assert await require_admin(i, "cmd", bot) is True
    i.followup.send.assert_not_called()


@pytest.mark.asyncio
async def test_require_mod_no_guild_returns_false():
    i = _mock_interaction(guild_id=None)
    bot = MagicMock()
    assert await require_mod(i, "cmd", bot) is False
    i.followup.send.assert_not_called()


@pytest.mark.asyncio
async def test_require_mod_granted_returns_true():
    i = _mock_interaction(guild_id=1)
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    assert await require_mod(i, "cmd", bot) is True
    i.followup.send.assert_not_called()


@pytest.mark.asyncio
async def test_require_admin_denied_sends_message():
    i = _mock_interaction(guild_id=1)
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    assert await require_admin(i, "cmd", bot) is False
    i.followup.send.assert_awaited_once_with("Admin required.", ephemeral=True)


@pytest.mark.asyncio
async def test_require_mod_denied_sends_message():
    i = _mock_interaction(guild_id=1)
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    assert await require_mod(i, "cmd", bot) is False
    i.followup.send.assert_awaited_once_with("Moderator or higher required.", ephemeral=True)


@pytest.mark.asyncio
async def test_require_super_admin_no_guild_returns_false():
    i = _mock_interaction(guild_id=None)
    bot = MagicMock()
    assert await require_super_admin(i, "cmd", bot) is False


@pytest.mark.asyncio
async def test_require_super_admin_denied_sends_message():
    i = _mock_interaction(guild_id=1)
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    assert await require_super_admin(i, "cmd", bot) is False
    i.followup.send.assert_awaited_once_with("❌ Super Admin required.", ephemeral=True)


@pytest.mark.asyncio
async def test_require_rcon_no_rcon_sends_message():
    i = _mock_interaction()
    bot = MagicMock(minecraft_rcon=None)
    assert await require_rcon(i, bot) is False
    i.followup.send.assert_awaited_once_with(
        "Minecraft whitelist is not configured for this server.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_require_guild_no_guild_sends_message():
    i = _mock_interaction(guild_id=None)
    assert await require_guild(i) is False
    i.followup.send.assert_awaited_once_with("❌ Server only.", ephemeral=True)


@pytest.mark.asyncio
async def test_require_guild_with_guild_returns_true():
    i = _mock_interaction(guild_id=1)
    assert await require_guild(i) is True
    i.followup.send.assert_not_called()


@pytest.mark.asyncio
async def test_execute_command_defers_and_calls_handler():
    i = _mock_interaction(guild_id=1)
    i.response = MagicMock()
    i.response.defer = AsyncMock()
    called = {"value": False}

    @execute_command()
    async def _cmd(interaction):
        called["value"] = True
        interaction.followup.send.assert_not_called()

    await _cmd(i)
    assert called["value"] is True
    i.response.defer.assert_awaited_once_with(ephemeral=True)


@pytest.mark.asyncio
async def test_execute_command_permission_check_short_circuits():
    i = _mock_interaction(guild_id=1)
    i.response = MagicMock()
    i.response.defer = AsyncMock()

    async def _deny(*args, **kwargs):
        return False

    called = {"value": False}

    @execute_command(permission_check=_deny)
    async def _cmd(interaction):
        called["value"] = True

    await _cmd(i)
    assert called["value"] is False
    i.response.defer.assert_awaited_once_with(ephemeral=True)


@pytest.mark.asyncio
async def test_execute_command_raw_error_message():
    i = _mock_interaction(guild_id=1)
    i.response = MagicMock()
    i.response.defer = AsyncMock()

    @execute_command(error_message="Error creating poll.", use_send_error=False)
    async def _cmd(interaction):
        raise RuntimeError("boom")

    await _cmd(i)
    i.followup.send.assert_awaited_once_with("Error creating poll.", ephemeral=True)


def test_get_interaction_prefers_keyword_argument():
    i = _mock_interaction(guild_id=1)
    i.response = MagicMock()
    i.followup = MagicMock()
    result = _get_interaction(tuple(), {"interaction": i})
    assert result is i


def test_get_interaction_raises_when_not_found():
    with pytest.raises(ValueError, match="Command interaction argument not found."):
        _get_interaction(tuple(), {})
