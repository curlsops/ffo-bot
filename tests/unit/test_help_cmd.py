from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from bot.commands.help_cmd import (
    HelpCommands,
    _build_command_detail_embed,
    _build_help_embed,
    _clip_field,
    _find_top_level_command,
    _format_parameters,
    _help_command_autocomplete,
    _normalize_help_query,
)


def test_normalize_help_query():
    assert _normalize_help_query(None) is None
    assert _normalize_help_query("  ") is None
    assert _normalize_help_query("FAQ") == "faq"
    assert _normalize_help_query("anon") == "anonymous"


def test_clip_field():
    assert _clip_field("hi") == "hi"
    out = _clip_field("x" * 500, max_len=100)
    assert out.endswith("...")
    assert len(out) == 100


def test_format_parameters_empty():
    @app_commands.command(name="z", description="z")
    async def z(interaction: discord.Interaction):
        pass

    assert _format_parameters(z) == "No options."


def test_format_parameters_fallback_without_describe():
    @app_commands.command(name="t", description="t")
    async def t(interaction: discord.Interaction, label: str):
        pass

    s = _format_parameters(t)
    assert "label" in s
    assert "Text." in s


def test_format_parameters_with_choices():
    lots = [app_commands.Choice(name=str(i), value=str(i)) for i in range(15)]

    @app_commands.command(name="t", description="t")
    @app_commands.describe(a="alpha")
    @app_commands.choices(b=lots)
    async def t(interaction: discord.Interaction, a: str, b: str):
        pass

    s = _format_parameters(t)
    assert "alpha" in s
    assert "Choices:" in s
    assert " …" in s


def test_find_top_level_with_real_command():
    @app_commands.command(name="ping", description="pong")
    async def ping_cb(interaction: discord.Interaction):
        pass

    bot = MagicMock()
    bot.tree.get_commands.return_value = [ping_cb]
    assert _find_top_level_command(bot, None, "ping") is ping_cb
    assert _find_top_level_command(bot, None, "missing") is None


def test_find_top_level_hidden_skipped():
    @app_commands.command(name="secret", description="x")
    async def secret_cb(interaction: discord.Interaction):
        pass

    secret_cb.hidden = True
    bot = MagicMock()
    bot.tree.get_commands.return_value = [secret_cb]
    assert _find_top_level_command(bot, None, "secret") is None


@pytest.mark.asyncio
async def test_help_command_autocomplete_filters():
    @app_commands.command(name="alpha", description="a")
    async def alpha(interaction: discord.Interaction):
        pass

    @app_commands.command(name="beta", description="b")
    async def beta(interaction: discord.Interaction):
        pass

    bot = MagicMock(spec=discord.ext.commands.Bot)
    bot.tree.get_commands.return_value = [beta, alpha]
    i = MagicMock()
    i.client = bot
    i.user = MagicMock()
    i.guild = None

    choices = await _help_command_autocomplete(i, "al")
    assert [c.value for c in choices] == ["alpha"]


@pytest.mark.asyncio
async def test_help_command_autocomplete_non_bot_client():
    i = MagicMock()
    i.client = object()
    assert await _help_command_autocomplete(i, "") == []


def test_build_command_detail_embed_leaf():
    @app_commands.command(name="giveaway", description="Gw management")
    @app_commands.describe(op="Operation")
    async def giveaway_cb(interaction: discord.Interaction, op: str):
        pass

    i = MagicMock()
    i.user = MagicMock()
    i.guild = None
    emb = _build_command_detail_embed(i, giveaway_cb)
    assert emb.title == "/giveaway"
    assert any(f.name == "Options" for f in emb.fields)


def _stub_callback_factory(n: int):
    async def stub(_interaction: discord.Interaction):
        pass

    stub.__name__ = f"stub_{n}"
    return stub


def test_build_command_detail_embed_group_truncates_subs():
    class SmallGroup(app_commands.Group):
        def __init__(self):
            super().__init__(name="sg", description="sub-group")

    bg = SmallGroup()
    for n in range(4):
        bg.add_command(
            app_commands.Command(
                name=f"s{n}",
                description=f"sub {n}",
                callback=_stub_callback_factory(n),
                parent=bg,
            )
        )

    i = MagicMock()
    i.user = MagicMock()
    i.guild = None
    with patch("bot.commands.help_cmd._MAX_DETAIL_SUB_FIELDS", 3):
        emb = _build_command_detail_embed(i, bg)
    assert len(emb.fields) == 3
    assert "4" in (emb.footer.text or "")


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


def test_build_help_embed_empty(mock_bot, mock_interaction):
    embed = _build_help_embed(mock_bot, mock_interaction)
    assert embed.title == "Commands"
    assert embed.fields == []


def test_build_help_embed_with_command(mock_bot, mock_interaction):
    cmd = MagicMock()
    cmd.name = "ping"
    cmd.description = "Pong"
    cmd.commands = []
    cmd.hidden = False
    cmd.default_member_permissions = None
    mock_bot.tree.get_commands.return_value = [cmd]
    embed = _build_help_embed(mock_bot, mock_interaction)
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "/ping"
    assert embed.fields[0].value == "Pong"


def test_build_help_embed_skips_context_menu(mock_bot, mock_interaction):
    cm = MagicMock(spec=discord.app_commands.ContextMenu)
    cm.name = "ctx"
    cm.description = "ctx desc"
    mock_bot.tree.get_commands.return_value = [cm]
    embed = _build_help_embed(mock_bot, mock_interaction)
    assert embed.fields == []


def test_build_help_embed_truncates_at_25_fields(mock_bot, mock_interaction):
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
    embed = _build_help_embed(mock_bot, mock_interaction)
    assert len(embed.fields) == 25
    assert "30" in (embed.footer.text or "")


@pytest.mark.asyncio
async def test_help_cog_with_command_shows_detail(mock_bot, mock_interaction):
    @app_commands.command(name="ping", description="pong")
    async def ping_cb(interaction: discord.Interaction):
        pass

    mock_bot.tree.get_commands.return_value = [ping_cb]
    mock_interaction.response.send_message = AsyncMock()
    cog = HelpCommands(mock_bot)
    await cog.help.callback(cog, mock_interaction, "ping")
    mock_interaction.response.send_message.assert_awaited_once()
    call_kw = mock_interaction.response.send_message.await_args.kwargs
    assert "embed" in call_kw
    assert call_kw["embed"].title == "/ping"


@pytest.mark.asyncio
async def test_help_cog_unknown_command(mock_bot, mock_interaction):
    mock_bot.tree.get_commands.return_value = []
    mock_interaction.response.send_message = AsyncMock()
    cog = HelpCommands(mock_bot)
    await cog.help.callback(cog, mock_interaction, "nope")
    mock_interaction.response.send_message.assert_awaited_once()
    assert "Unknown" in (mock_interaction.response.send_message.await_args.args[0] or "")
