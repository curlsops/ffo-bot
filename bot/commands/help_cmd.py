import discord
from discord import AppCommandOptionType, app_commands
from discord.ext import commands

_MAX_EMBED_FIELDS = 25
_MAX_DETAIL_SUB_FIELDS = 25
_MAX_FIELD_VALUE = 1020

_HELP_ALIASES: dict[str, str] = {
    "anon": "anonymous",
}

_CommandOrGroup = app_commands.Command | app_commands.Group


def _interaction_member(interaction: discord.Interaction) -> discord.Member | None:
    if isinstance(interaction.user, discord.Member):
        return interaction.user
    if interaction.guild:
        return interaction.guild.get_member(interaction.user.id)
    return None


def _normalize_help_query(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    return _HELP_ALIASES.get(s, s)


def _parameters_in_order(cmd: _CommandOrGroup) -> list:
    raw = cmd.parameters
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw)


def _clip_field(text: str, max_len: int = _MAX_FIELD_VALUE) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _is_meaningful_option_description(description: str | None) -> bool:
    if not description:
        return False
    d = description.strip()
    return bool(d) and d not in ("…", "...")


_OPTION_TYPE_FALLBACK: dict[AppCommandOptionType, str] = {
    AppCommandOptionType.subcommand: "Subcommand to run next.",
    AppCommandOptionType.subcommand_group: "Nested command group.",
    AppCommandOptionType.string: "Text.",
    AppCommandOptionType.integer: "Integer.",
    AppCommandOptionType.boolean: "Boolean toggle.",
    AppCommandOptionType.user: "Member.",
    AppCommandOptionType.channel: "Channel.",
    AppCommandOptionType.role: "Role.",
    AppCommandOptionType.mentionable: "User or role.",
    AppCommandOptionType.number: "Number (may be decimal).",
    AppCommandOptionType.attachment: "File attachment.",
}


def _fallback_parameter_line(param) -> str:
    t = param.type
    return _OPTION_TYPE_FALLBACK.get(t, "Slash option value.")


def _format_parameters(cmd: _CommandOrGroup) -> str:
    param_list = _parameters_in_order(cmd)
    if not param_list:
        return "No options."
    lines: list[str] = []
    for param in param_list:
        line = f"**{param.name}** — {'required' if param.required else 'optional'}"
        if _is_meaningful_option_description(param.description):
            line += f"\n{param.description}"
        else:
            line += f"\n{_fallback_parameter_line(param)}"
        choices = getattr(param, "choices", None) or []
        if choices:
            labels = [ch.name for ch in param.choices[:12]]
            suffix = " …" if len(param.choices) > 12 else ""
            line += f"\nChoices: {', '.join(labels)}{suffix}"
        lines.append(line)
    return "\n\n".join(lines)


def _user_can_see_command(
    cmd: app_commands.Command | app_commands.Group | app_commands.ContextMenu,
    member: discord.Member | None,
) -> bool:
    if member is None:
        return True
    perms = getattr(cmd, "default_member_permissions", None)
    if perms is None:
        return True
    return bool(member.guild_permissions >= perms)


def _find_top_level_command(
    bot: commands.Bot,
    member: discord.Member | None,
    name: str,
) -> app_commands.Command | app_commands.Group | None:
    for cmd in bot.tree.get_commands():
        if cmd.name.lower() != name:
            continue
        if isinstance(cmd, app_commands.ContextMenu):
            return None
        if isinstance(cmd, app_commands.Group):
            return cmd if _user_can_see_command(cmd, member) else None
        if getattr(cmd, "hidden", False):
            return None
        return cmd if _user_can_see_command(cmd, member) else None
    return None


def _visible_top_level_names(bot: commands.Bot, member: discord.Member | None) -> list[str]:
    names: list[str] = []
    for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
        if isinstance(cmd, app_commands.ContextMenu):
            continue
        if isinstance(cmd, app_commands.Group):
            if _user_can_see_command(cmd, member):
                names.append(cmd.name)
        elif not getattr(cmd, "hidden", False) and _user_can_see_command(cmd, member):
            names.append(cmd.name)
    return names


async def _help_command_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    bot = interaction.client
    if not isinstance(bot, commands.Bot):
        return []
    member = _interaction_member(interaction)
    names = _visible_top_level_names(bot, member)
    cur = (current or "").lower()
    filtered = [n for n in names if not cur or cur in n.lower()]
    return [app_commands.Choice(name=n, value=n) for n in filtered[:25]]


def _build_command_detail_embed(
    interaction: discord.Interaction,
    cmd: app_commands.Command | app_commands.Group,
) -> discord.Embed:
    member = _interaction_member(interaction)
    if isinstance(cmd, app_commands.Group):
        embed = discord.Embed(
            title=f"/{cmd.name}",
            description=cmd.description or "—",
            color=discord.Color.blue(),
        )
        visible_subs = sorted(
            [s for s in cmd.commands if _user_can_see_command(s, member)],
            key=lambda c: c.name,
        )
        footer_extra = ""
        if len(visible_subs) > _MAX_DETAIL_SUB_FIELDS:
            footer_extra = f" First {_MAX_DETAIL_SUB_FIELDS} of {len(visible_subs)} subcommands."
            visible_subs = visible_subs[:_MAX_DETAIL_SUB_FIELDS]
        for sub in visible_subs:
            sub_header = f"/{cmd.name} {sub.name}"
            body = (sub.description or "—") + "\n\n" + _format_parameters(sub)
            embed.add_field(name=sub_header, value=_clip_field(body), inline=False)
        embed.set_footer(text=f"Run with `/` in this server.{footer_extra}")
        return embed

    embed = discord.Embed(
        title=f"/{cmd.name}",
        description=cmd.description or "—",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Options", value=_clip_field(_format_parameters(cmd)), inline=False)
    embed.set_footer(text="Run with `/` in this server.")
    return embed


def _build_help_embed(bot: commands.Bot, interaction: discord.Interaction) -> discord.Embed:
    embed = discord.Embed(
        title="Commands",
        description="Slash commands available on this server.",
        color=discord.Color.blue(),
    )
    member = _interaction_member(interaction)
    fields = []
    for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
        if isinstance(cmd, app_commands.ContextMenu):
            continue
        if isinstance(cmd, app_commands.Group):
            if not _user_can_see_command(cmd, member):
                continue
            for sub in cmd.commands:
                if not _user_can_see_command(sub, member):
                    continue
                fields.append((f"/{cmd.name} {sub.name}", (sub.description or "—")[:100]))
        elif not getattr(cmd, "hidden", False) and _user_can_see_command(cmd, member):
            fields.append((f"/{cmd.name}", (cmd.description or "—")[:100]))
    for name, value in fields[:_MAX_EMBED_FIELDS]:
        embed.add_field(name=name, value=value, inline=False)
    footer = "Optional: set `command` for one command. Use `/` to run."
    if len(fields) > _MAX_EMBED_FIELDS:
        footer += f" Showing {_MAX_EMBED_FIELDS}/{len(fields)}."
    embed.set_footer(text=footer)
    return embed


class HelpCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="List commands or show help for one command")
    @app_commands.describe(command="Top-level command (omit for list)")
    @app_commands.autocomplete(command=_help_command_autocomplete)
    async def help(self, interaction: discord.Interaction, command: str | None = None):
        normalized = _normalize_help_query(command)
        if normalized is None:
            embed = _build_help_embed(self.bot, interaction)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        target = _find_top_level_command(self.bot, _interaction_member(interaction), normalized)
        if target is None:
            await interaction.response.send_message(
                "Unknown command. Use `/help` for the full list.",
                ephemeral=True,
            )
            return
        embed = _build_command_detail_embed(interaction, target)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCommands(bot))
