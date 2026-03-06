from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.auth.command_helpers import (
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
