import discord
from discord import app_commands
from discord.ext import commands

_MAX_EMBED_FIELDS = 25


def _build_help_embed(bot: commands.Bot) -> discord.Embed:
    embed = discord.Embed(
        title="Commands",
        description="Slash commands available on this server.",
        color=discord.Color.blue(),
    )
    fields = []
    for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.commands:
                fields.append((f"/{cmd.name} {sub.name}", (sub.description or "—")[:100]))
        elif not getattr(cmd, "hidden", False):
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
        embed = _build_help_embed(self.bot)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCommands(bot))
