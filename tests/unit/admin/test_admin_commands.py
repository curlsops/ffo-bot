import importlib.metadata
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.commands.admin import AdminCommands, RegisterCommandsView


def _admin_bot(admin=True, notifier_success=True, current_notify_channel_id=None):
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=admin)
    bot.latency = 0.05
    bot._register_server = AsyncMock()
    bot.notifier = MagicMock()
    bot.notifier.get_notify_channel_id = AsyncMock(return_value=current_notify_channel_id)
    bot.notifier.get_notify_channel = AsyncMock(return_value=MagicMock(send=AsyncMock()))
    bot.notifier.set_notify_channel = AsyncMock(return_value=notifier_success)
    bot.notifier.notify_notify_channel_changed = AsyncMock()
    bot.tree = MagicMock()
    bot.tree.copy_global_to = MagicMock()
    bot.tree.sync = AsyncMock(return_value=[MagicMock()])
    bot.tree.clear_commands = MagicMock()
    return bot


def _view_button(view, label):
    return next(c for c in view.children if getattr(c, "label", None) == label)


def _interaction(guild_id=111, user_id=222, channel_id=333):
    i = MagicMock()
    i.guild_id = guild_id
    i.user.id = user_id
    i.guild = MagicMock(id=guild_id)
    i.channel_id = channel_id
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.followup.send = AsyncMock()
    return i


@pytest.mark.asyncio
async def test_register_commands_view_guild_mismatch():
    bot = _admin_bot()
    view = RegisterCommandsView(bot, guild_id=999)
    i = _interaction(guild_id=111)
    btn = _view_button(view, "Register (this server)")
    await btn.callback(i)
    i.response.send_message.assert_awaited_once()
    assert "same server" in i.response.send_message.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_register_commands_view_register_guild_success():
    bot = _admin_bot()
    view = RegisterCommandsView(bot, guild_id=111)
    i = _interaction(guild_id=111)
    btn = _view_button(view, "Register (this server)")
    await btn.callback(i)
    bot.tree.copy_global_to.assert_called_once_with(guild=i.guild)
    bot.tree.sync.assert_awaited_once_with(guild=i.guild)
    assert "Registered" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_register_commands_view_register_guild_failure():
    bot = _admin_bot()
    bot.tree.sync = AsyncMock(side_effect=RuntimeError("sync failed"))
    view = RegisterCommandsView(bot, guild_id=111)
    i = _interaction(guild_id=111)
    btn = _view_button(view, "Register (this server)")
    await btn.callback(i)
    assert "Failed" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_register_commands_view_register_global_success():
    bot = _admin_bot()
    view = RegisterCommandsView(bot, guild_id=111)
    i = _interaction()
    btn = _view_button(view, "Register (global)")
    await btn.callback(i)
    bot.tree.sync.assert_awaited_once_with()
    assert "globally" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_register_commands_view_register_global_failure():
    bot = _admin_bot()
    bot.tree.sync = AsyncMock(side_effect=RuntimeError("no"))
    view = RegisterCommandsView(bot, guild_id=111)
    i = _interaction()
    btn = _view_button(view, "Register (global)")
    await btn.callback(i)
    assert "Failed" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_register_commands_view_clear_guild_wrong_server():
    bot = _admin_bot()
    view = RegisterCommandsView(bot, guild_id=999)
    i = _interaction(guild_id=111)
    btn = _view_button(view, "Clear (this server)")
    await btn.callback(i)
    i.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_commands_view_clear_guild_success():
    bot = _admin_bot()
    view = RegisterCommandsView(bot, guild_id=111)
    i = _interaction(guild_id=111)
    btn = _view_button(view, "Clear (this server)")
    await btn.callback(i)
    bot.tree.clear_commands.assert_called_once_with(guild=i.guild)
    assert "cleared" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_register_commands_view_clear_guild_failure():
    bot = _admin_bot()
    bot.tree.sync = AsyncMock(side_effect=ValueError("x"))
    view = RegisterCommandsView(bot, guild_id=111)
    i = _interaction(guild_id=111)
    btn = _view_button(view, "Clear (this server)")
    await btn.callback(i)
    assert "Failed" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_version_package_not_found_uses_env(monkeypatch):
    bot = _admin_bot()
    monkeypatch.setenv("FFO_BOT_VERSION", "9.9.9")
    i = _interaction()
    with patch(
        "bot.commands.admin.importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError(),
    ):
        cog = AdminCommands(bot)
        await cog.admin_group.version.callback(cog.admin_group, i)
    assert "9.9.9" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_notify_disable_sends_embed_to_old_channel():
    bot = _admin_bot(current_notify_channel_id=555)
    notify_ch = MagicMock(send=AsyncMock())
    bot.notifier.get_notify_channel = AsyncMock(return_value=notify_ch)
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=None)
    notify_ch.send.assert_awaited()
    embed = notify_ch.send.call_args[1]["embed"]
    assert isinstance(embed, discord.Embed)
    assert "disabled" in embed.description.lower()


@pytest.mark.asyncio
async def test_notify_disable_embed_send_failure_ignored():
    bot = _admin_bot(current_notify_channel_id=555)
    notify_ch = MagicMock(send=AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no")))
    bot.notifier.get_notify_channel = AsyncMock(return_value=notify_ch)
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=None)
    bot.notifier.set_notify_channel.assert_awaited()


@pytest.mark.asyncio
async def test_notify_channel_not_admin():
    bot = _admin_bot()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    ch = MagicMock()
    ch.id = 1
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=ch)
    assert "Admin" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_notify_disable_when_old_channel_unresolved_skips_embed():
    bot = _admin_bot(current_notify_channel_id=555)
    bot.notifier.get_notify_channel = AsyncMock(return_value=None)
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=None)
    bot.notifier.set_notify_channel.assert_awaited()


@pytest.mark.asyncio
async def test_register_commands_super_admin():
    bot = _admin_bot()
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.register_commands.callback(g, i)
    assert i.followup.send.call_args[1].get("view") is not None


@pytest.mark.asyncio
async def test_register_commands_no_guild_after_super_admin():
    bot = _admin_bot()
    i = _interaction()
    i.guild_id = None
    with patch("bot.commands.admin.require_super_admin", new_callable=AsyncMock, return_value=True):
        g = AdminCommands(bot).admin_group
        await g.register_commands.callback(g, i)
    assert "Server only" in str(i.followup.send.call_args)


@pytest.mark.asyncio
async def test_register_commands_not_super_admin():
    bot = _admin_bot()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.register_commands.callback(g, i)
    assert "Super Admin" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_version_not_admin():
    bot = _admin_bot()
    bot.permission_checker.check_role = AsyncMock(return_value=False)
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.version.callback(g, i)
    assert "Admin" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_notify_channel_no_guild():
    bot = _admin_bot()
    i = _interaction()
    i.guild = None
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=MagicMock())
    assert "Server only" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_notify_channel_already_set_to_same_channel():
    bot = _admin_bot(current_notify_channel_id=999)
    ch = MagicMock()
    ch.id = 999
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=ch)
    assert "already" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_notify_channel_already_disabled():
    bot = _admin_bot(current_notify_channel_id=None)
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=None)
    assert "already" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_notify_channel_set_fails():
    bot = _admin_bot(current_notify_channel_id=1)
    bot.notifier.set_notify_channel = AsyncMock(return_value=False)
    i = _interaction()
    ch = MagicMock()
    ch.id = 2
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=ch)
    assert "Failed" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_notify_channel_success_new_channel():
    bot = _admin_bot(current_notify_channel_id=None)
    ch = MagicMock()
    ch.id = 3
    ch.mention = "<#3>"
    i = _interaction()
    g = AdminCommands(bot).admin_group
    await g.notify_channel.callback(g, i, channel=ch)
    bot.notifier.notify_notify_channel_changed.assert_awaited()
    assert ch.mention in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_ping():
    bot = _admin_bot()
    i = _interaction()
    cog = AdminCommands(bot)
    await cog.ping.callback(cog, i)
    assert "Pong" in i.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_cog_load_unload():
    bot = MagicMock()
    bot.tree.add_command = MagicMock()
    bot.tree.remove_command = MagicMock()
    cog = AdminCommands(bot)
    await cog.cog_load()
    bot.tree.add_command.assert_called_once_with(cog.admin_group)
    await cog.cog_unload()
    bot.tree.remove_command.assert_called_once_with("admin")


@pytest.mark.asyncio
async def test_admin_setup():
    from bot.commands import admin as admin_mod

    bot = MagicMock()
    bot.add_cog = AsyncMock()
    await admin_mod.setup(bot)
    bot.add_cog.assert_awaited_once()
