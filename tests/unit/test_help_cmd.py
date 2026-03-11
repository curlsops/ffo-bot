from unittest.mock import MagicMock

import pytest

from bot.commands.help_cmd import HelpCommands, _build_help_embed


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.tree.get_commands.return_value = []
    return bot


def test_build_help_embed_empty(mock_bot):
    embed = _build_help_embed(mock_bot)
    assert embed.title == "Commands"
    assert embed.fields == []


def test_build_help_embed_with_command(mock_bot):
    cmd = MagicMock()
    cmd.name = "ping"
    cmd.description = "Pong"
    cmd.commands = []
    cmd.hidden = False
    mock_bot.tree.get_commands.return_value = [cmd]
    embed = _build_help_embed(mock_bot)
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "/ping"
    assert embed.fields[0].value == "Pong"
