import discord
from discord import app_commands
from discord.ext import commands


def _build_help_embed(bot: commands.Bot) -> discord.Embed:
    embed = discord.Embed(
        title="Commands",
        description="Slash commands available on this server.",
        color=discord.Color.blue(),
    )
    for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.commands:
                name = f"/{cmd.name} {sub.name}"
                desc = sub.description or "—"
                embed.add_field(name=name, value=desc[:100], inline=False)
        elif not getattr(cmd, "hidden", False):
            name = f"/{cmd.name}"
            desc = cmd.description or "—"
            embed.add_field(name=name, value=desc[:100], inline=False)
    embed.set_footer(text="Use / before a command to see its options.")
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
