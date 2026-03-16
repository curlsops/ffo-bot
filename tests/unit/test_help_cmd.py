from unittest.mock import MagicMock

import pytest

from bot.commands.help_cmd import HelpCommands, _build_help_embed


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.tree.get_commands.return_value = []
    return bot


@pytest.fixture
def mock_interaction():
    i = MagicMock()
    i.user = MagicMock()
    i.guild = None
    return i


@pytest.mark.asyncio
async def test_build_help_embed_empty(mock_bot, mock_interaction):
    embed = await _build_help_embed(mock_bot, mock_interaction)
    assert embed.title == "Commands"
    assert embed.fields == []


@pytest.mark.asyncio
async def test_build_help_embed_with_command(mock_bot, mock_interaction):
    cmd = MagicMock()
    cmd.name = "ping"
    cmd.description = "Pong"
    cmd.commands = []
    cmd.hidden = False
    cmd.default_member_permissions = None
    mock_bot.tree.get_commands.return_value = [cmd]
    embed = await _build_help_embed(mock_bot, mock_interaction)
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "/ping"
    assert embed.fields[0].value == "Pong"


@pytest.mark.asyncio
async def test_build_help_embed_truncates_at_25_fields(mock_bot, mock_interaction):
    cmds = []
    for i in range(30):
        c = MagicMock()
        c.name = f"cmd{i}"
        c.commands = []
        c.description = f"Desc {i}"
        c.hidden = False
        c.default_member_permissions = None
        cmds.append(c)
    mock_bot.tree.get_commands.return_value = cmds
    embed = await _build_help_embed(mock_bot, mock_interaction)
    assert len(embed.fields) == 25
    assert "30" in (embed.footer.text or "")
