from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from bot.commands.anonymous import (
    ANONYMOUS_BUTTON_CUSTOM_ID,
    ANONYMOUS_EMBED_COLOR,
    AnonymousCommands,
    AnonymousPostButtonView,
    AnonymousPostModal,
    _anonymous_submission_embed,
    _post_destination,
    _prepare_anonymous_submission,
    _process_anonymous_submission,
    _truncate_for_discord,
)
from tests.helpers import mock_db_ctx


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
    view = AnonymousPostButtonView(post_channel_id=123, board_channel_id=500, bot=mock_bot)
    i = MagicMock()
    i.response.send_modal = AsyncMock()
    for item in view.children:
        if isinstance(item, discord.ui.Button) and item.custom_id == ANONYMOUS_BUTTON_CUSTOM_ID:
            await item.callback(i)
            break
    i.response.send_modal.assert_called_once()
    modal = i.response.send_modal.call_args[0][0]
    assert isinstance(modal, AnonymousPostModal)
    assert modal.post_channel_id == 123
    assert modal.board_channel_id == 500


def test_process_submission_empty(mock_bot):
    err, body = _process_anonymous_submission("   ", 1, mock_bot)
    assert err == "Message cannot be empty."
    assert body is None


def test_process_submission_channel_not_found(mock_bot):
    mock_bot.get_channel.return_value = None
    err, body = _process_anonymous_submission("Hello", 1, mock_bot)
    assert err == "Anonymous post channel not found."
    assert body is None


def test_process_submission_success(mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    mock_bot.get_channel.return_value = channel
    err, body = _process_anonymous_submission("Hello world", 1, mock_bot)
    assert err is None
    assert body == "Hello world"


def test_process_submission_passthrough_text(mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    mock_bot.get_channel.return_value = channel
    err, out = _process_anonymous_submission("My name is Bob", 1, mock_bot)
    assert err is None
    assert out == "My name is Bob"


def test_prepare_submission_returns_channel(mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    mock_bot.get_channel.return_value = channel
    err, body, returned_channel = _prepare_anonymous_submission("Hello world", 1, mock_bot)
    assert err is None
    assert body == "Hello world"
    assert returned_channel is channel


def test_truncate_for_discord_truncates_when_needed():
    msg = "x" * 3000
    truncated = _truncate_for_discord(msg)
    assert len(truncated) == 2000
    assert truncated.endswith("...")


@pytest.mark.asyncio
async def test_modal_on_submit_success(cog, mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    mock_bot.get_channel.return_value = channel

    modal = AnonymousPostModal(post_channel_id=1, board_channel_id=2, bot=mock_bot)
    with patch.object(type(modal.children[0]), "value", "Hello world"):
        i = MagicMock()
        i.user = MagicMock()
        i.user.send = AsyncMock()
        i.response.send_message = AsyncMock()
        await modal.on_submit(i)

    channel.send.assert_called_once()
    _, kwargs = channel.send.call_args
    assert "embed" in kwargs
    assert kwargs["embed"].title == "Anonymous"
    assert kwargs["embed"].description == "Hello world"
    assert kwargs["embed"].color == ANONYMOUS_EMBED_COLOR
    assert kwargs["embed"].footer.text == "Follow Server Rules · <#2> to make your own post"
    i.response.send_message.assert_called_once_with(
        "Your message was posted anonymously.", ephemeral=True
    )


def test_anonymous_submission_embed():
    emb = _anonymous_submission_embed("hello", 999)
    assert emb.title == "Anonymous"
    assert emb.description == "hello"
    assert emb.color == ANONYMOUS_EMBED_COLOR
    assert emb.footer.text == "Follow Server Rules · <#999> to make your own post"


def test_cog_unload(cog):
    cog.bot.tree.remove_command = MagicMock()
    cog.cog_unload()
    cog.bot.tree.remove_command.assert_called_once_with("anonymous")


_OP_SETUP = app_commands.Choice(name="Setup", value="setup")
_OP_REMOVE = app_commands.Choice(name="Remove", value="remove")


def test_post_destination_non_postable(mock_bot):
    mock_bot.get_channel.return_value = MagicMock()
    assert _post_destination(mock_bot, 1) is None


@pytest.mark.asyncio
async def test_anonymous_cmd_server_only_no_guild(cog):
    i = MagicMock()
    i.guild_id = None
    i.channel_id = 2
    i.user = MagicMock(id=9)
    i.response.send_message = AsyncMock()
    await cog.anonymous_cmd.callback(i, _OP_SETUP, None)
    i.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_anonymous_cmd_server_only_no_channel(cog):
    i = MagicMock()
    i.guild_id = 1
    i.channel_id = None
    i.user = MagicMock(id=9)
    i.response.send_message = AsyncMock()
    await cog.anonymous_cmd.callback(i, _OP_SETUP, None)
    i.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_anonymous_cmd_denied_not_admin(cog, mock_bot):
    mock_bot.permission_checker.check_role = AsyncMock(return_value=False)
    i = MagicMock()
    i.guild_id = 1
    i.channel_id = 2
    i.user = MagicMock(id=9)
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    await cog.anonymous_cmd.callback(i, _OP_SETUP, None)


@pytest.mark.asyncio
async def test_modal_on_submit_error_empty_logs(mock_bot):
    modal = AnonymousPostModal(post_channel_id=1, board_channel_id=2, bot=mock_bot)
    with patch.object(type(modal.children[0]), "value", "   "):
        i = MagicMock()
        i.guild_id = 1
        i.user = MagicMock(id=3)
        i.response.send_message = AsyncMock()
        await modal.on_submit(i)
    i.response.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_modal_on_submit_http_exception(mock_bot):
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "fail"))
    mock_bot.get_channel.return_value = channel
    modal = AnonymousPostModal(post_channel_id=1, board_channel_id=2, bot=mock_bot)
    with patch.object(type(modal.children[0]), "value", "Hello"):
        i = MagicMock()
        i.guild_id = 1
        i.user = MagicMock(id=3)
        i.response.send_message = AsyncMock()
        await modal.on_submit(i)
    assert "Failed" in i.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_setup_cannot_send_in_channel(cog, mock_bot):
    post_target = MagicMock()
    post_target.id = 99
    post_target.permissions_for = MagicMock(return_value=MagicMock(send_messages=False))
    i = MagicMock()
    i.guild_id = 1
    i.channel_id = 50
    i.guild = MagicMock(me=MagicMock())
    i.channel = MagicMock()
    i.followup.send = AsyncMock()
    await cog._handle_setup(i, post_channel=post_target)
    assert "permission" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_setup_skips_perm_gate_when_no_permissions_for(cog, mock_bot):
    post_target = SimpleNamespace(id=42)
    i = MagicMock()
    i.guild_id = 1
    i.channel_id = 50
    i.guild = MagicMock(me=MagicMock())
    i.channel = MagicMock(send=AsyncMock(return_value=MagicMock(id=1)))
    i.followup.send = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    await cog._handle_setup(i, post_channel=post_target)
    conn.execute.assert_awaited()


@pytest.mark.asyncio
async def test_handle_setup_guild_me_none_skips_send_warning(cog, mock_bot):
    post_target = MagicMock()
    post_target.id = 77
    post_target.permissions_for = MagicMock(return_value=MagicMock(send_messages=False))
    i = MagicMock()
    i.guild_id = 1
    i.channel_id = 50
    i.guild = MagicMock(me=None)
    i.channel = MagicMock(send=AsyncMock(return_value=MagicMock(id=2)))
    i.followup.send = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    await cog._handle_setup(i, post_channel=post_target)
    mock_bot.db_pool.acquire.assert_called()


@pytest.mark.asyncio
async def test_handle_setup_save_failure(cog, mock_bot, interaction):
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("db"))
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    interaction.guild = MagicMock(me=MagicMock())
    interaction.channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))

    with patch("bot.commands.anonymous.send_error", new_callable=AsyncMock) as err:
        await cog._handle_setup(interaction, post_channel=None)
    err.assert_awaited()


@pytest.mark.asyncio
async def test_handle_setup_posts_and_followup_location_note(cog, mock_bot, interaction):
    other_ch = MagicMock()
    other_ch.id = 777
    other_ch.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    interaction.guild = MagicMock(me=MagicMock())
    conn = MagicMock()
    conn.execute = AsyncMock()
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    await cog._handle_setup(interaction, post_channel=other_ch)
    assert interaction.channel_id != other_ch.id
    text = interaction.followup.send.call_args[0][0]
    assert "Posts go to" in text or "777" in text


@pytest.mark.asyncio
async def test_handle_remove_no_config(cog, mock_bot, interaction):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    await cog._handle_remove(interaction)
    assert "No anonymous" in interaction.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_remove_success(cog, mock_bot, interaction):
    row = {"channel_id": 10, "message_id": 20}
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock()
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    ch = MagicMock()
    msg = MagicMock(delete=AsyncMock())
    ch.fetch_message = AsyncMock(return_value=msg)
    mock_bot.get_channel.return_value = ch
    await cog._handle_remove(interaction)
    msg.delete.assert_awaited()


@pytest.mark.asyncio
async def test_delete_setup_message_no_channel(cog, mock_bot):
    mock_bot.get_channel.return_value = None
    row = {"channel_id": 1, "message_id": 2}
    await cog._delete_setup_message(row)


@pytest.mark.asyncio
async def test_delete_setup_message_not_found(cog, mock_bot):
    ch = MagicMock()
    ch.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    mock_bot.get_channel.return_value = ch
    await cog._delete_setup_message({"channel_id": 1, "message_id": 2})


@pytest.mark.asyncio
async def test_delete_setup_message_http_exception(cog, mock_bot):
    ch = MagicMock()
    ch.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "x"))
    mock_bot.get_channel.return_value = ch
    await cog._delete_setup_message({"channel_id": 1, "message_id": 2})


@pytest.mark.asyncio
async def test_handle_remove_outer_exception(cog, mock_bot, interaction):
    mock_bot.db_pool.acquire = MagicMock(side_effect=RuntimeError("pool"))

    with patch("bot.commands.anonymous.send_error", new_callable=AsyncMock) as err:
        await cog._handle_remove(interaction)
    err.assert_awaited()


@pytest.mark.asyncio
async def test_setup_via_command_callback(cog, mock_bot, interaction):
    conn = MagicMock()
    conn.execute = AsyncMock()
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    interaction.guild = MagicMock(me=MagicMock())
    interaction.channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    await cog.anonymous_cmd.callback(interaction, _OP_SETUP, None)


@pytest.mark.asyncio
async def test_remove_via_command_callback(cog, mock_bot, interaction):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    mock_bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    await cog.anonymous_cmd.callback(interaction, _OP_REMOVE, None)


@pytest.mark.asyncio
async def test_cog_load_and_setup(mock_bot):
    mock_bot.tree.add_command = MagicMock()
    cog = AnonymousCommands(mock_bot)
    await cog.cog_load()
    mock_bot.tree.add_command.assert_called_once()

    from bot.commands import anonymous as anon_mod

    mock_bot.add_cog = AsyncMock()
    await anon_mod.setup(mock_bot)
    mock_bot.add_cog.assert_awaited_once()
