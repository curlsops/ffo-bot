import discord
from discord import app_commands
from discord.ext import commands

_MAX_EMBED_FIELDS = 25


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


async def _build_help_embed(bot: commands.Bot, interaction: discord.Interaction) -> discord.Embed:
    embed = discord.Embed(
        title="Commands",
        description="Slash commands available on this server.",
        color=discord.Color.blue(),
    )
    member = (
        interaction.user
        if isinstance(interaction.user, discord.Member)
        else (interaction.guild.get_member(interaction.user.id) if interaction.guild else None)
    )
    fields = []
    for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
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
    footer = "Use / before a command to see its options."
    if len(fields) > _MAX_EMBED_FIELDS:
        footer += f" (Showing first {_MAX_EMBED_FIELDS} of {len(fields)}.)"
    embed.set_footer(text=footer)
    return embed


class HelpCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="List available commands")
    async def help(self, interaction: discord.Interaction):
        embed = await _build_help_embed(self.bot, interaction)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCommands(bot))
