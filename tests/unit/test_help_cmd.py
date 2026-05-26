from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import AppCommandOptionType, app_commands

from bot.commands.help_cmd import (
    HelpCommands,
    _build_command_detail_embed,
    _build_help_embed,
    _clip_field,
    _fallback_parameter_line,
    _find_top_level_command,
    _format_parameters,
    _group_help_entries,
    _help_command_autocomplete,
    _interaction_member,
    _is_meaningful_option_description,
    _normalize_help_query,
    _operation_expand_entries,
    _parameters_in_order,
    _user_can_see_command,
    _visible_top_level_names,
)

_ADMIN_PERM = discord.Permissions(administrator=True)


def _member_no_admin() -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.guild_permissions = discord.Permissions()
    return member


def _admin_only_command(name: str, description: str = "x"):
    @app_commands.command(name=name, description=description)
    @app_commands.default_permissions(administrator=True)
    async def cb(interaction: discord.Interaction):
        pass

    cb.default_member_permissions = _ADMIN_PERM
    return cb


def test_normalize_help_query():
    assert _normalize_help_query(None) is None
    assert _normalize_help_query("  ") is None
    assert _normalize_help_query("FAQ") == "faq"
    assert _normalize_help_query("anon") == "anon"


def test_clip_field():
    assert _clip_field("hi") == "hi"
    out = _clip_field("x" * 500, max_len=100)
    assert out.endswith("...")
    assert len(out) == 100


def test_interaction_member_returns_member_directly():
    member = MagicMock(spec=discord.Member)
    i = MagicMock()
    i.user = member
    assert _interaction_member(i) is member


def test_interaction_member_fetches_from_guild_when_user_not_member():
    member = MagicMock(spec=discord.Member)
    i = MagicMock()
    i.user = MagicMock(spec=discord.User)
    i.guild = MagicMock()
    i.guild.get_member.return_value = member
    assert _interaction_member(i) is member


def test_parameters_in_order_accepts_dict_mapping():
    cmd = MagicMock()
    a = MagicMock(name="a")
    b = MagicMock(name="b")
    cmd.parameters = {"x": a, "y": b}
    assert _parameters_in_order(cmd) == [a, b]


def test_operation_expand_requires_visibility():
    @app_commands.command(name="locked", description="x")
    @app_commands.describe(operation="Pick")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(
        operation=[
            app_commands.Choice(name="One", value="1"),
            app_commands.Choice(name="Two", value="2"),
        ]
    )
    async def locked_cb(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        pass

    locked_cb.default_member_permissions = _ADMIN_PERM
    assert _operation_expand_entries(locked_cb, _member_no_admin()) is None


def test_operation_expand_requires_two_or_more_choices():
    @app_commands.command(name="one", description="x")
    @app_commands.describe(operation="Pick")
    @app_commands.choices(operation=[app_commands.Choice(name="Only", value="only")])
    async def one_cb(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        pass

    assert _operation_expand_entries(one_cb, None) is None


def test_operation_expand_uses_option_description_when_meaningful():
    @app_commands.command(name="gw", description="Giveaway")
    @app_commands.describe(operation="Operation help text")
    @app_commands.choices(
        operation=[
            app_commands.Choice(name="Start", value="start"),
            app_commands.Choice(name="Stop", value="stop"),
        ]
    )
    async def gw_cb(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        pass

    rows = _operation_expand_entries(gw_cb, None)
    assert rows is not None
    assert "Operation help text" in rows[0][1]


def test_group_help_entries_empty_when_group_invisible():
    group = MagicMock(spec=app_commands.Group)
    group.name = "g"
    group.description = "d"
    group.walk_commands.return_value = []
    group.default_member_permissions = discord.Permissions(administrator=True)
    member = MagicMock()
    member.guild_permissions = discord.Permissions()
    assert _group_help_entries(group, member) == []


def test_is_meaningful_option_description():
    assert _is_meaningful_option_description(None) is False
    assert _is_meaningful_option_description("") is False
    assert _is_meaningful_option_description("…") is False
    assert _is_meaningful_option_description("ok") is True


def test_fallback_parameter_line_unknown_type():
    p = MagicMock()
    p.type = MagicMock()
    assert _fallback_parameter_line(p) == "Slash option value."


def test_fallback_parameter_line_known_type():
    p = MagicMock()
    p.type = AppCommandOptionType.integer
    assert "Integer" in _fallback_parameter_line(p)


def test_find_top_level_skips_context_menu():
    cm = MagicMock(spec=discord.app_commands.ContextMenu)
    cm.name = "menu"
    bot = MagicMock()
    bot.tree.get_commands.return_value = [cm]
    assert _find_top_level_command(bot, None, "menu") is None


def test_find_top_level_returns_matching_group():
    class Grp(app_commands.Group):
        def __init__(self):
            super().__init__(name="music", description="m")

    grp = Grp()
    bot = MagicMock()
    bot.tree.get_commands.return_value = [grp]
    assert _find_top_level_command(bot, None, "music") is grp


def test_visible_top_level_names_sorted_and_filtered():
    cm = MagicMock(spec=discord.app_commands.ContextMenu)
    cm.name = "ctx"
    hidden = MagicMock()
    hidden.name = "secret"
    hidden.hidden = True
    vis = MagicMock()
    vis.name = "alpha"
    vis.hidden = False
    vis.default_member_permissions = None
    bot = MagicMock()
    bot.tree.get_commands.return_value = [cm, hidden, vis]
    assert _visible_top_level_names(bot, None) == ["alpha"]


def test_visible_top_level_includes_group_when_permitted():
    class Grp(app_commands.Group):
        def __init__(self):
            super().__init__(name="grp", description="g")

    grp = Grp()
    bot = MagicMock()
    bot.tree.get_commands.return_value = [grp]
    assert _visible_top_level_names(bot, None) == ["grp"]


def test_user_can_see_command_false_when_member_lacks_permissions():
    cmd = MagicMock()
    cmd.default_member_permissions = discord.Permissions(administrator=True)
    member = MagicMock()
    member.guild_permissions = discord.Permissions()
    assert _user_can_see_command(cmd, member) is False


def test_operation_expand_skips_params_until_operation():
    @app_commands.command(name="mix", description="Mix")
    @app_commands.describe(extra="Extra field", operation="Pick")
    @app_commands.choices(
        operation=[
            app_commands.Choice(name="A", value="a"),
            app_commands.Choice(name="B", value="b"),
        ]
    )
    async def mix_cb(
        interaction: discord.Interaction,
        extra: str,
        operation: app_commands.Choice[str],
    ):
        pass

    rows = _operation_expand_entries(mix_cb, None)
    assert rows is not None
    assert len(rows) == 2


def test_group_help_entries_skips_nested_group_children():
    class Inner(app_commands.Group):
        def __init__(self):
            super().__init__(name="inner", description="inner")

        @app_commands.command(name="deep", description="deep leaf")
        async def deep(self, interaction: discord.Interaction):
            pass

    class Outer(app_commands.Group):
        def __init__(self):
            super().__init__(name="outer", description="outer")
            self.add_command(Inner())

    outer = Outer()
    rows = _group_help_entries(outer, None)
    names = [r[0] for r in rows]
    assert "/outer inner deep" in names


def test_group_help_entries_skips_leaf_when_member_cannot_see():
    leaf_cb = _admin_only_command("secret_leaf", "hidden leaf")

    class Outer(app_commands.Group):
        def __init__(self):
            super().__init__(name="outer", description="outer")

    outer = Outer()
    outer.add_command(leaf_cb)
    assert _group_help_entries(outer, _member_no_admin()) == []


@pytest.mark.parametrize(
    "check",
    [
        lambda bot, member: _visible_top_level_names(bot, member),
        lambda bot, member: [f.name for f in _build_help_embed(bot, MagicMock(user=member)).fields],
    ],
)
def test_skips_admin_command_when_member_lacks_permission(check):
    bot = MagicMock()
    bot.tree.get_commands.return_value = [_admin_only_command("modonly", "mod")]
    result = check(bot, _member_no_admin())
    assert result == [] or all(name != "/modonly" for name in result)


def test_visible_top_level_skips_group_when_member_lacks_permission():
    class Grp(app_commands.Group):
        def __init__(self):
            super().__init__(name="secrets", description="s")

    grp = Grp()
    grp.default_member_permissions = discord.Permissions(administrator=True)
    bot = MagicMock()
    bot.tree.get_commands.return_value = [grp]
    assert _visible_top_level_names(bot, _member_no_admin()) == []


def test_build_help_embed_skips_hidden_top_level_command(mock_bot, mock_interaction):
    @app_commands.command(name="ghost", description="hidden")
    async def ghost_cb(interaction: discord.Interaction):
        pass

    ghost_cb.hidden = True
    mock_bot.tree.get_commands.return_value = [ghost_cb]
    embed = _build_help_embed(mock_bot, mock_interaction)
    assert all(f.name != "/ghost" for f in embed.fields)


def test_build_help_embed_includes_visible_top_level_command(mock_bot, mock_interaction):
    @app_commands.command(name="plain", description="Plain command")
    async def plain_cb(interaction: discord.Interaction):
        pass

    mock_bot.tree.get_commands.return_value = [plain_cb]
    embed = _build_help_embed(mock_bot, mock_interaction)
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "/plain"


def test_build_command_detail_embed_group_without_truncation_footer(mock_bot, mock_interaction):
    class SmallGroup(app_commands.Group):
        def __init__(self):
            super().__init__(name="sg", description="sub-group")

    bg = SmallGroup()
    for n in range(2):
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
    emb = _build_command_detail_embed(i, bg)
    assert len(emb.fields) == 2
    assert "First" not in (emb.footer.text or "")


def test_build_help_embed_expanded_operation_rows(mock_bot, mock_interaction):
    @app_commands.command(name="gw", description="Giveaway tool")
    @app_commands.describe(operation="Which operation")
    @app_commands.choices(
        operation=[
            app_commands.Choice(name="Start", value="start"),
            app_commands.Choice(name="Reroll", value="reroll"),
        ]
    )
    async def gw_cb(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        pass

    mock_bot.tree.get_commands.return_value = [gw_cb]
    embed = _build_help_embed(mock_bot, mock_interaction)
    names = [f.name for f in embed.fields]
    assert "/gw start" in names and "/gw reroll" in names


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


def test_find_top_level_returns_matching_command():
    @app_commands.command(name="ping", description="pong")
    async def ping_cb(interaction: discord.Interaction):
        pass

    bot = MagicMock()
    bot.tree.get_commands.return_value = [ping_cb]
    assert _find_top_level_command(bot, None, "ping") is ping_cb


def test_find_top_level_missing_returns_none():
    @app_commands.command(name="ping", description="pong")
    async def ping_cb(interaction: discord.Interaction):
        pass

    bot = MagicMock()
    bot.tree.get_commands.return_value = [ping_cb]
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
    assert emb.fields[0].name == "/sg s0"


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


def test_operation_expand_entries_two_choices():
    @app_commands.command(name="gw", description="Giveaway")
    @app_commands.describe(operation="Pick op")
    @app_commands.choices(
        operation=[
            app_commands.Choice(name="Start", value="start"),
            app_commands.Choice(name="Reroll", value="reroll"),
        ]
    )
    async def gw_cb(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        pass

    rows = _operation_expand_entries(gw_cb, None)
    assert rows is not None
    assert [r[0] for r in rows] == ["/gw start", "/gw reroll"]


def test_group_help_entries_nested_qualified_names():
    class Inner(app_commands.Group):
        def __init__(self):
            super().__init__(name="inner", description="inner grp")

        @app_commands.command(name="leaf", description="leaf cmd")
        async def leaf(self, interaction: discord.Interaction):
            pass

    class Outer(app_commands.Group):
        def __init__(self):
            super().__init__(name="out", description="outer")
            self.add_command(Inner())

    g = Outer()
    rows = _group_help_entries(g, None)
    assert len(rows) == 1
    assert rows[0][0] == "/out inner leaf"


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
    args = mock_interaction.response.send_message.await_args
    msg = (args.args[0] if args.args else args.kwargs.get("content")) or ""
    assert "Unknown" in msg


def test_operation_expand_skips_meaningless_operation_description():
    @app_commands.command(name="gw", description="Giveaway")
    @app_commands.describe(operation="…")
    @app_commands.choices(
        operation=[
            app_commands.Choice(name="Start", value="start"),
            app_commands.Choice(name="Reroll", value="reroll"),
        ]
    )
    async def gw_cb(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        pass

    rows = _operation_expand_entries(gw_cb, None)
    assert rows is not None
    assert rows[0][1] == "Start"


def test_user_can_see_true_when_default_permissions_none():
    cmd = MagicMock()
    cmd.default_member_permissions = None
    assert _user_can_see_command(cmd, MagicMock()) is True


def test_user_can_see_true_when_member_meets_permissions():
    cmd = MagicMock()
    cmd.default_member_permissions = discord.Permissions(send_messages=True)
    member = MagicMock()
    member.guild_permissions = discord.Permissions(send_messages=True)
    assert _user_can_see_command(cmd, member) is True


def test_build_help_embed_includes_group_fields(mock_bot, mock_interaction):
    class Inner(app_commands.Group):
        def __init__(self):
            super().__init__(name="inner", description="inner")

        @app_commands.command(name="leaf", description="leaf cmd")
        async def leaf(self, interaction: discord.Interaction):
            pass

    class Outer(app_commands.Group):
        def __init__(self):
            super().__init__(name="out", description="outer")
            self.add_command(Inner())

    mock_bot.tree.get_commands.return_value = [Outer()]
    embed = _build_help_embed(mock_bot, mock_interaction)
    assert any("/out inner leaf" in f.name for f in embed.fields)


@pytest.mark.asyncio
async def test_help_cog_lists_commands_when_no_query(mock_bot, mock_interaction):
    mock_interaction.response.send_message = AsyncMock()
    cog = HelpCommands(mock_bot)
    await cog.help.callback(cog, mock_interaction, None)
    mock_interaction.response.send_message.assert_awaited_once()
    assert mock_interaction.response.send_message.await_args.kwargs["embed"].title == "Commands"


@pytest.mark.asyncio
async def test_help_setup_adds_cog():
    bot = MagicMock()
    bot.add_cog = AsyncMock()

    from bot.commands.help_cmd import setup

    await setup(bot)
    bot.add_cog.assert_awaited_once()
    assert isinstance(bot.add_cog.await_args.args[0], HelpCommands)
