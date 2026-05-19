import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, send_error

logger = logging.getLogger(__name__)

ANONYMOUS_BUTTON_CUSTOM_ID = "anonymous:post"
MAX_MESSAGE_LENGTH = 2000
ANONYMOUS_EMBED_COLOR = discord.Color.from_rgb(197, 154, 74)

ANONYMOUS_OPERATION_CHOICES = [
    app_commands.Choice(name="Setup", value="setup"),
    app_commands.Choice(name="Remove", value="remove"),
]


def _post_destination(
    bot: commands.Bot, channel_id: int
) -> discord.TextChannel | discord.Thread | None:
    channel = bot.get_channel(channel_id)
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        return channel
    return None


def _truncate_for_discord(message: str) -> str:
    if len(message) <= MAX_MESSAGE_LENGTH:
        return message
    return message[: MAX_MESSAGE_LENGTH - 3] + "..."


def _anonymous_submission_embed(body: str, board_channel_id: int) -> discord.Embed:
    embed = discord.Embed(
        title="Anonymous",
        description=body,
        color=ANONYMOUS_EMBED_COLOR,
    )
    embed.set_footer(text=f"Follow Server Rules · <#{board_channel_id}> to make your own post")
    return embed


def _prepare_anonymous_submission(
    raw_text: str,
    post_channel_id: int,
    bot: commands.Bot,
) -> tuple[str | None, str | None, discord.TextChannel | discord.Thread | None]:
    text = raw_text.strip()
    if not text:
        return ("Message cannot be empty.", None, None)

    body = _truncate_for_discord(text)
    channel = _post_destination(bot, post_channel_id)
    if not channel:
        return ("Anonymous post channel not found.", None, None)

    return (None, body, channel)


def _process_anonymous_submission(
    raw_text: str,
    post_channel_id: int,
    bot: commands.Bot,
) -> tuple[str | None, str | None]:
    error, body, _ = _prepare_anonymous_submission(raw_text, post_channel_id, bot)
    if error:
        return (error, None)
    return (None, body)


class AnonymousPostModal(discord.ui.Modal, title="Compose"):
    def __init__(self, post_channel_id: int, board_channel_id: int, bot: commands.Bot):
        super().__init__()
        self.post_channel_id = post_channel_id
        self.board_channel_id = board_channel_id
        self.bot = bot
        self.add_item(
            discord.ui.TextInput(
                label="Message",
                style=discord.TextStyle.paragraph,
                placeholder="What should appear in the channel",
                required=True,
                min_length=1,
                max_length=MAX_MESSAGE_LENGTH,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_text = self.children[0].value
        error, body, channel = _prepare_anonymous_submission(
            raw_text,
            self.post_channel_id,
            self.bot,
        )
        if error:
            logger.warning(
                "anonymous post rejected: guild_id=%s user_id=%s post_channel_id=%s reason=%s",
                interaction.guild_id,
                interaction.user.id if interaction.user else None,
                self.post_channel_id,
                error,
            )
            await interaction.response.send_message(error, ephemeral=True)
            return

        try:
            await channel.send(embed=_anonymous_submission_embed(body, self.board_channel_id))
            logger.info(
                "anonymous post sent: guild_id=%s post_channel_id=%s user_id=%s length=%s",
                interaction.guild_id,
                self.post_channel_id,
                interaction.user.id if interaction.user else None,
                len(body),
            )
            await interaction.response.send_message(
                "Your message was posted anonymously.", ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(
                "anonymous post failed: guild_id=%s post_channel_id=%s user_id=%s error=%s",
                interaction.guild_id,
                self.post_channel_id,
                interaction.user.id if interaction.user else None,
                e,
            )
            await interaction.response.send_message("Failed to post message.", ephemeral=True)


class AnonymousPostButtonView(discord.ui.View):
    def __init__(self, post_channel_id: int, board_channel_id: int, bot: commands.Bot):
        super().__init__(timeout=None)
        self.post_channel_id = post_channel_id
        self.board_channel_id = board_channel_id
        self.bot = bot

    @discord.ui.button(
        label="Compose",
        style=discord.ButtonStyle.secondary,
        custom_id=ANONYMOUS_BUTTON_CUSTOM_ID,
    )
    async def post_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            AnonymousPostModal(self.post_channel_id, self.board_channel_id, self.bot)
        )


def _anonymous_command(cog: "AnonymousCommands"):
    @app_commands.command(
        name="anonymous",
        description="Admins: set up or remove the anonymous post board.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        operation="Setup or remove the anonymous post button",
        post_channel=("Channel where messages are posted (default: same channel as the button)"),
    )
    @app_commands.choices(operation=ANONYMOUS_OPERATION_CHOICES)
    async def anonymous_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
        post_channel: discord.TextChannel | None = None,
    ):
        # Defer first so require_admin and admin-only flows can use followup.send (matches other
        # admin commands, e.g. reaction roles).
        if not interaction.guild_id or not interaction.channel_id:
            logger.info(
                "anonymous command rejected (not in server): user_id=%s",
                interaction.user.id if interaction.user else None,
            )
            await interaction.response.send_message("❌ Server only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if not await require_admin(interaction, "anonymous", cog.bot):
            logger.info(
                "anonymous command denied (not admin): guild_id=%s user_id=%s",
                interaction.guild_id,
                interaction.user.id if interaction.user else None,
            )
            return

        post_ch_id = post_channel.id if post_channel else None
        logger.info(
            "anonymous command: op=%s guild_id=%s user_id=%s post_channel_id=%s",
            operation.value,
            interaction.guild_id,
            interaction.user.id if interaction.user else None,
            post_ch_id,
        )

        if operation.value == "setup":
            await cog._handle_setup(interaction, post_channel=post_channel)
            return

        await cog._handle_remove(interaction)

    return anonymous_cmd


class AnonymousCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.anonymous_cmd = _anonymous_command(self)

    async def _save_channel_config(
        self,
        guild_id: int,
        board_channel_id: int,
        message_id: int,
        post_channel_id: int,
    ) -> None:
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO anonymous_post_channels
                    (server_id, channel_id, message_id, post_channel_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (server_id) DO UPDATE
                SET channel_id = EXCLUDED.channel_id,
                    message_id = EXCLUDED.message_id,
                    post_channel_id = EXCLUDED.post_channel_id
                """,
                guild_id,
                board_channel_id,
                message_id,
                post_channel_id,
            )

    async def _get_channel_config(self, guild_id: int):
        async with self.bot.db_pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT channel_id, message_id, post_channel_id
                FROM anonymous_post_channels
                WHERE server_id = $1
                """,
                guild_id,
            )

    async def _clear_channel_config(self, guild_id: int) -> None:
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM anonymous_post_channels WHERE server_id = $1",
                guild_id,
            )

    async def _handle_setup(
        self,
        interaction: discord.Interaction,
        post_channel: discord.TextChannel | None = None,
    ) -> None:
        guild = interaction.guild
        post_target = post_channel or interaction.channel
        if guild and post_target is not None and hasattr(post_target, "permissions_for"):
            me = guild.me
            if me is not None and not post_target.permissions_for(me).send_messages:
                logger.warning(
                    "anonymous setup: bot cannot send in post channel guild_id=%s post_channel_id=%s",
                    interaction.guild_id,
                    post_target.id,
                )
                await interaction.followup.send(
                    "I need permission to send messages in the channel where posts will go.",
                    ephemeral=True,
                )
                return

        post_channel_id = post_target.id

        embed = discord.Embed(
            title="Anon Board",
            description=(
                f"**Compose** to post to <#{post_channel_id}>.\n\n"
                "Your text is sent as you write it, but it comes from the bot with nothing "
                "attached to you."
            ),
            color=ANONYMOUS_EMBED_COLOR,
        )
        embed.set_footer(text="Follow Server Rules")
        board_channel_id = interaction.channel_id
        view = AnonymousPostButtonView(post_channel_id, board_channel_id, self.bot)
        msg = await interaction.channel.send(embed=embed, view=view)
        try:
            await self._save_channel_config(
                interaction.guild_id,
                interaction.channel_id,
                msg.id,
                post_channel_id,
            )
        except Exception as e:
            logger.exception("Failed to save anonymous post channel: %s", e)
            await send_error(interaction, "Failed to save configuration.")
            return

        location_note = (
            f" Posts go to <#{post_channel_id}>"
            if post_channel_id != interaction.channel_id
            else ""
        )
        await interaction.followup.send(
            f"Anonymous post button added. Message ID: {msg.id}.{location_note}",
            ephemeral=True,
        )
        logger.info(
            "anonymous board setup: guild_id=%s board_channel_id=%s post_channel_id=%s "
            "board_message_id=%s by_user_id=%s",
            interaction.guild_id,
            interaction.channel_id,
            post_channel_id,
            msg.id,
            interaction.user.id if interaction.user else None,
        )

    async def _handle_remove(self, interaction: discord.Interaction) -> None:
        try:
            row = await self._get_channel_config(interaction.guild_id)
            if not row:
                logger.info(
                    "anonymous remove: no config guild_id=%s user_id=%s",
                    interaction.guild_id,
                    interaction.user.id if interaction.user else None,
                )
                await interaction.followup.send(
                    "No anonymous post channel configured.",
                    ephemeral=True,
                )
                return

            await self._clear_channel_config(interaction.guild_id)
            await self._delete_setup_message(row)
            await interaction.followup.send(
                "Anonymous post removed.",
                ephemeral=True,
            )
            logger.info(
                "anonymous board removed: guild_id=%s by_user_id=%s",
                interaction.guild_id,
                interaction.user.id if interaction.user else None,
            )
        except Exception as e:
            logger.exception("Failed to remove anonymous post: %s", e)
            await send_error(interaction, "Failed to remove.")

    async def _delete_setup_message(self, row) -> None:
        channel = self.bot.get_channel(row["channel_id"])
        if not channel:
            return
        try:
            msg = await channel.fetch_message(row["message_id"])
            await msg.delete()
        except discord.NotFound:
            return
        except discord.HTTPException as e:
            logger.warning("Failed to delete anonymous post message: %s", e)

    async def cog_load(self):
        self.bot.tree.add_command(self.anonymous_cmd)

    def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.anonymous_cmd.name)


async def setup(bot):
    await bot.add_cog(AnonymousCommands(bot))
