from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.cooldown import CommandCooldown, with_cooldown


@pytest.mark.asyncio
async def test_cooldown_allows_first():
    c = CommandCooldown(rate=1, per=60.0)
    allowed, retry = await c.check(1, 2, "ping")
    assert allowed is True
    assert retry == 0.0


@pytest.mark.asyncio
async def test_cooldown_blocks_second():
    c = CommandCooldown(rate=1, per=60.0)
    await c.check(1, 2, "ping")
    allowed, retry = await c.check(1, 2, "ping")
    assert allowed is False
    assert retry > 0


@pytest.mark.asyncio
async def test_with_cooldown_skips_when_no_guild():
    with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
        check = with_cooldown(rate=1, per=60.0)
    i = MagicMock()
    i.guild_id = None
    i.command = MagicMock(qualified_name="test")
    assert await check(i) is True


@pytest.mark.asyncio
async def test_with_cooldown_skips_when_no_command():
    with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
        check = with_cooldown(rate=1, per=60.0)
    i = MagicMock()
    i.guild_id = 123
    i.command = None
    assert await check(i) is True


@pytest.mark.asyncio
async def test_with_cooldown_blocks_and_sends_message():
    with patch("bot.utils.cooldown.app_commands.check", lambda pred: pred):
        check = with_cooldown(rate=1, per=60.0)
    i = MagicMock()
    i.guild_id = 123
    i.user = MagicMock(id=456)
    i.command = MagicMock(qualified_name="spam")
    i.response.send_message = AsyncMock()
    assert await check(i) is True
    assert await check(i) is False
    i.response.send_message.assert_awaited_once()
