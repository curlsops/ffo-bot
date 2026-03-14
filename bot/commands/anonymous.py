import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, send_error
from bot.utils.anonymize import anonymize_text

logger = logging.getLogger(__name__)

ANONYMOUS_BUTTON_CUSTOM_ID = "anonymous:post"
MAX_MESSAGE_LENGTH = 2000

ANONYMOUS_OPERATION_CHOICES = [
    app_commands.Choice(name="Setup", value="setup"),
    app_commands.Choice(name="Remove", value="remove"),
]


def _process_anonymous_submission(
    raw_text: str,
    channel_id: int,
    bot: commands.Bot,
) -> tuple[str | None, str | None]:
    text = raw_text.strip()
    if not text:
        return ("Message cannot be empty.", None)

    anonymized = anonymize_text(text)
    if len(anonymized) > MAX_MESSAGE_LENGTH:
        anonymized = anonymized[: MAX_MESSAGE_LENGTH - 3] + "..."

    channel = bot.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return ("Anonymous post channel not found.", None)

    return (None, anonymized)


class AnonymousPostModal(discord.ui.Modal, title="Post anonymously"):
    def __init__(self, channel_id: int, bot: commands.Bot):
        super().__init__()
        self.channel_id = channel_id
        self.bot = bot
        self.add_item(
            discord.ui.TextInput(
                label="Your message",
                style=discord.TextStyle.paragraph,
                placeholder="Your anonymous message...",
                required=True,
                min_length=1,
                max_length=MAX_MESSAGE_LENGTH,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_text = self.children[0].value.strip()
        error, anonymized = _process_anonymous_submission(raw_text, self.channel_id, self.bot)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        try:
            channel = self.bot.get_channel(self.channel_id)
            if channel:
                await channel.send(anonymized)
            await interaction.response.send_message(
                "Your message was posted anonymously.", ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error("Failed to post anonymous message: %s", e)
            await interaction.response.send_message("Failed to post message.", ephemeral=True)


class AnonymousPostButtonView(discord.ui.View):
    def __init__(self, channel_id: int, bot: commands.Bot):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.bot = bot

    @discord.ui.button(
        label="Post anonymously",
        style=discord.ButtonStyle.primary,
        custom_id=ANONYMOUS_BUTTON_CUSTOM_ID,
    )
    async def post_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(AnonymousPostModal(self.channel_id, self.bot))


def _anonymous_command(cog: "AnonymousCommands"):
    @app_commands.command(
        name="anonymous",
        description="Anonymous post setup. Provide operation.",
    )
    @app_commands.guild_only()
    @app_commands.describe(operation="Setup or remove the anonymous post button")
    @app_commands.choices(operation=ANONYMOUS_OPERATION_CHOICES)
    async def anonymous_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
    ):
        if not interaction.guild_id or not interaction.channel_id:
            await send_error(interaction, "Server only.")
            return
        if not await require_admin(interaction, "anonymous", cog.bot):
            return

        await interaction.response.defer(ephemeral=True)

        if operation.value == "setup":
            embed = discord.Embed(
                title="Anonymous Post",
                description="Click the button below to post a message anonymously. Names will be anonymized.",
                color=discord.Color.blurple(),
            )
            view = AnonymousPostButtonView(interaction.channel_id, cog.bot)
            msg = await interaction.channel.send(embed=embed, view=view)
            try:
                async with cog.bot.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO anonymous_post_channels (server_id, channel_id, message_id)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (server_id) DO UPDATE
                        SET channel_id = EXCLUDED.channel_id, message_id = EXCLUDED.message_id
                        """,
                        interaction.guild_id,
                        interaction.channel_id,
                        msg.id,
                    )
                await interaction.followup.send(
                    f"Anonymous post button added. Message ID: {msg.id}",
                    ephemeral=True,
                )
            except Exception as e:
                logger.exception("Failed to save anonymous post channel: %s", e)
                await send_error(interaction, "Failed to save configuration.")
        else:
            try:
                async with cog.bot.db_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT channel_id, message_id FROM anonymous_post_channels WHERE server_id = $1",
                        interaction.guild_id,
                    )
                    if not row:
                        await interaction.followup.send(
                            "No anonymous post channel configured.",
                            ephemeral=True,
                        )
                        return
                    await conn.execute(
                        "DELETE FROM anonymous_post_channels WHERE server_id = $1",
                        interaction.guild_id,
                    )

                channel = cog.bot.get_channel(row["channel_id"])
                if channel:
                    try:
                        msg = await channel.fetch_message(row["message_id"])
                        await msg.delete()
                    except discord.NotFound:  # message already deleted
                        pass
                    except discord.HTTPException as e:
                        logger.warning("Failed to delete anonymous post message: %s", e)

                await interaction.followup.send(
                    "Anonymous post removed.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.exception("Failed to remove anonymous post: %s", e)
                await send_error(interaction, "Failed to remove.")

    return anonymous_cmd


class AnonymousCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.anonymous_cmd = _anonymous_command(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.anonymous_cmd)

    def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.anonymous_cmd.name)


async def setup(bot):
    await bot.add_cog(AnonymousCommands(bot))
