from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.commands.anonymous import (
    ANONYMOUS_BUTTON_CUSTOM_ID,
    AnonymousCommands,
    AnonymousPostButtonView,
    AnonymousPostModal,
    _process_anonymous_submission,
)


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.db_pool = MagicMock()
    bot.get_channel = MagicMock(return_value=None)
    return bot


@pytest.fixture
def cog(mock_bot):
    return AnonymousCommands(mock_bot)


@pytest.fixture
def interaction():
    i = MagicMock()
    i.guild_id = 1
    i.channel_id = 2
    i.channel = MagicMock()
    i.channel.send = AsyncMock(return_value=MagicMock(id=999))
    i.response = MagicMock()
    i.response.defer = AsyncMock()
    i.response.send_modal = AsyncMock()
    i.followup = MagicMock()
    i.followup.send = AsyncMock()
    return i


@pytest.fixture
def db_ctx():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    @MagicMock
    async def acquire():
        class Ctx:
            __aenter__ = AsyncMock(return_value=conn)
            __aexit__ = AsyncMock(return_value=None)

        return Ctx()

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


@pytest.mark.asyncio
async def test_post_button_sends_modal(cog, mock_bot):
    view = AnonymousPostButtonView(channel_id=123, bot=mock_bot)
    i = MagicMock()
    i.response.send_modal = AsyncMock()
    for item in view.children:
        if isinstance(item, discord.ui.Button) and item.custom_id == ANONYMOUS_BUTTON_CUSTOM_ID:
            await item.callback(i)
            break
    i.response.send_modal.assert_called_once()
    modal = i.response.send_modal.call_args[0][0]
    assert isinstance(modal, AnonymousPostModal)
    assert modal.channel_id == 123


def test_process_submission_empty(mock_bot):
    err, anonymized = _process_anonymous_submission("   ", 1, mock_bot)
    assert err == "Message cannot be empty."
    assert anonymized is None


def test_process_submission_channel_not_found(mock_bot):
    mock_bot.get_channel.return_value = None
    err, anonymized = _process_anonymous_submission("Hello", 1, mock_bot)
    assert err == "Anonymous post channel not found."
    assert anonymized is None


def test_process_submission_success(mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    mock_bot.get_channel.return_value = channel
    err, anonymized = _process_anonymous_submission("Hello world", 1, mock_bot)
    assert err is None
    assert anonymized == "Hello world"


def test_process_submission_anonymizes(mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    mock_bot.get_channel.return_value = channel
    err, anonymized = _process_anonymous_submission("My name is Bob", 1, mock_bot)
    assert err is None
    assert "Bob" not in anonymized
    assert "My name is" in anonymized


@pytest.mark.asyncio
async def test_modal_on_submit_success(cog, mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    mock_bot.get_channel.return_value = channel

    modal = AnonymousPostModal(channel_id=1, bot=mock_bot)
    with patch.object(type(modal.children[0]), "value", "Hello world"):
        i = MagicMock()
        i.user = MagicMock()
        i.user.send = AsyncMock()
        i.response.send_message = AsyncMock()
        await modal.on_submit(i)

    channel.send.assert_called_once_with("Hello world")
    i.response.send_message.assert_called_once_with(
        "Your message was posted anonymously.", ephemeral=True
    )


def test_cog_unload(cog):
    cog.bot.tree.remove_command = MagicMock()
    cog.cog_unload()
    cog.bot.tree.remove_command.assert_called_once_with("anonymous")
