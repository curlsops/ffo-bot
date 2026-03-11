import logging

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, send_error
from bot.utils.autocomplete import cached_autocomplete
from bot.utils.pagination import ListPaginatedView
from bot.utils.regex_validator import RegexValidationError
from bot.utils.validation import InputValidator, ValidationError
from config.constants import Constants

logger = logging.getLogger(__name__)

CACHE_REACTBOT_PHRASES = "reactbot_phrases:{server_id}"

REACTBOT_OPERATION_CHOICES = [
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="List", value="list"),
    app_commands.Choice(name="Remove", value="remove"),
]


def _invalidate_reactbot_cache(cache, server_id: int) -> None:
    if cache:
        cache.delete(CACHE_REACTBOT_PHRASES.format(server_id=server_id))


async def _fetch_reactbot_phrases(pool, guild_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT phrase, emoji FROM phrase_reactions
               WHERE server_id = $1 AND is_active = true
               ORDER BY match_count DESC LIMIT 25""",
            guild_id,
        )


def _reactbot_phrases_to_choices(rows: list[dict], current: str) -> list[app_commands.Choice[str]]:
    choices = []
    for row in rows:
        phrase = row["phrase"]
        emoji = row["emoji"]
        if not current or current.lower() in phrase.lower():
            display = f"{phrase} → {emoji}"
            if len(display) > 100:
                display = display[:97] + "..."
            choices.append(app_commands.Choice(name=display, value=phrase))
    return choices


async def _reactbot_phrase_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return await cached_autocomplete(
        interaction,
        current,
        CACHE_REACTBOT_PHRASES,
        _fetch_reactbot_phrases,
        _reactbot_phrases_to_choices,
        ttl=Constants.CACHE_TTL,
        log_prefix="Reactbot phrase",
    )


def _reactbot_command(cog: "ReactBotCommands"):
    @app_commands.command(
        name="reactbot",
        description="Phrase reaction management. Provide operation.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        operation="Add, List, or Remove a phrase reaction",
        phrase="Regex pattern (Add/Remove only)",
        emoji="Emoji to react with (Add only)",
    )
    @app_commands.choices(operation=REACTBOT_OPERATION_CHOICES)
    @app_commands.autocomplete(phrase=_reactbot_phrase_autocomplete)
    async def reactbot_cmd(
        interaction: discord.Interaction,
        operation: app_commands.Choice[str],
        phrase: str | None = None,
        emoji: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if operation.value == "list":
            try:
                cache_key = CACHE_REACTBOT_PHRASES.format(server_id=interaction.guild_id)
                rows = cog.bot.cache.get(cache_key) if cog.bot.cache else None
                if rows is None:
                    async with cog.bot.db_pool.acquire() as conn:
                        rows = await conn.fetch(
                            "SELECT phrase, emoji, match_count FROM phrase_reactions WHERE server_id = $1 AND is_active = true ORDER BY match_count DESC",
                            interaction.guild_id,
                        )
                    rows = [dict(r) for r in rows]
                    if cog.bot.cache:
                        cog.bot.cache.set(cache_key, rows, ttl=Constants.CACHE_TTL)
                if not rows:
                    await send_error(interaction, "No phrase reactions configured.")
                    return

                def fmt(r):
                    return f"• `{r['phrase']}` → {r['emoji']} ({r['match_count']} matches)"

                view = ListPaginatedView(rows, "**Phrase Reactions:**", fmt)
                await interaction.followup.send(
                    view._format_page(),
                    view=view,
                    ephemeral=True,
                )
            except Exception as e:
                logger.error("reactbot list error: %s", e, exc_info=True)
                await send_error(interaction, "Error fetching reactions.")
            return

        if operation.value == "add":
            if not await require_admin(interaction, "reactbot", cog.bot):
                return
            if not phrase or not emoji:
                await send_error(interaction, "Phrase and emoji required for Add.")
                return
            try:
                phrase = InputValidator.validate_phrase_pattern(phrase)
                emoji = InputValidator.validate_emoji(emoji)
                await cog.bot.phrase_matcher.validate_pattern(phrase)

                emoji_valid, emoji_error = await cog._validate_emoji_accessible(interaction, emoji)
                if not emoji_valid:
                    await send_error(interaction, emoji_error)
                    return

                async with cog.bot.db_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO phrase_reactions (server_id, phrase, emoji, created_by) VALUES ($1, $2, $3, $4)",
                        interaction.guild_id,
                        phrase,
                        emoji,
                        interaction.user.id,
                    )
                cog.bot.phrase_matcher.invalidate_cache(interaction.guild_id)
                _invalidate_reactbot_cache(cog.bot.cache, interaction.guild_id)
                await interaction.followup.send(f"✅ Added: `{phrase}` → {emoji}", ephemeral=True)
                if cog.bot.metrics:
                    cog.bot.metrics.commands_executed.labels(
                        command_name="reactbot add",
                        server_id=str(interaction.guild_id),
                        status="success",
                    ).inc()
            except asyncpg.UniqueViolationError:
                await send_error(
                    interaction,
                    f"This exact phrase + emoji combination already exists: `{phrase}` → {emoji}",
                )
            except (ValidationError, RegexValidationError) as e:
                await send_error(interaction, str(e))
            except Exception as e:
                logger.error("reactbot add error: %s", e, exc_info=True)
                await send_error(interaction, "Error processing command.")
            return

        if operation.value == "remove":
            if not await require_admin(interaction, "reactbot", cog.bot):
                return
            if not phrase:
                await send_error(interaction, "Phrase required for Remove.")
                return
            try:
                async with cog.bot.db_pool.acquire() as conn:
                    result = await conn.execute(
                        "UPDATE phrase_reactions SET is_active = false WHERE server_id = $1 AND phrase = $2 AND is_active = true",
                        interaction.guild_id,
                        phrase,
                    )
                if result == "UPDATE 0":
                    await send_error(interaction, f"Not found: `{phrase}`")
                    return
                cog.bot.phrase_matcher.invalidate_cache(interaction.guild_id)
                _invalidate_reactbot_cache(cog.bot.cache, interaction.guild_id)
                await interaction.followup.send(f"✅ Removed: `{phrase}`", ephemeral=True)
            except Exception as e:
                logger.error("reactbot remove error: %s", e, exc_info=True)
                await send_error(interaction, "Error processing command.")

    return reactbot_cmd


class ReactBotCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reactbot_cmd = _reactbot_command(self)

    async def _validate_emoji_accessible(
        self, interaction: discord.Interaction, emoji_str: str
    ) -> tuple[bool, str]:
        if emoji_str.startswith("<") and emoji_str.endswith(">"):
            parts = emoji_str.strip("<>").split(":")
            if len(parts) >= 3:
                try:
                    emoji_id = int(parts[2])
                    emoji_obj = self.bot.get_emoji(emoji_id)
                    if emoji_obj is None:
                        return (
                            False,
                            f"❌ Cannot access emoji {emoji_str}. The bot must be in the server where this emoji exists.",
                        )
                    if not emoji_obj.is_usable():
                        return False, f"❌ Emoji {emoji_str} is not usable by the bot."
                except ValueError:
                    pass
        return True, ""

    async def cog_load(self):
        self.bot.tree.add_command(self.reactbot_cmd)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.reactbot_cmd.name)


async def setup(bot):
    await bot.add_cog(ReactBotCommands(bot))
