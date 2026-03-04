import logging

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.pagination import ListPaginatedView
from bot.utils.regex_validator import RegexValidationError
from bot.utils.validation import InputValidator, ValidationError
from config.constants import Role

logger = logging.getLogger(__name__)


CACHE_REACTBOT_PHRASES = "reactbot_phrases:{server_id}"


def _invalidate_reactbot_cache(cache, server_id: int) -> None:
    if cache:
        cache.delete(CACHE_REACTBOT_PHRASES.format(server_id=server_id))


async def _reactbot_phrase_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    try:
        bot = interaction.client
        cache_key = CACHE_REACTBOT_PHRASES.format(server_id=interaction.guild_id)
        rows = bot.cache.get(cache_key) if bot.cache else None
        if rows is None:
            async with bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT phrase, emoji FROM phrase_reactions
                       WHERE server_id = $1 AND is_active = true
                       ORDER BY match_count DESC LIMIT 25""",
                    interaction.guild_id,
                )
            rows = [dict(r) for r in rows]
            if bot.cache:
                bot.cache.set(cache_key, rows, ttl=300)
        choices = []
        for row in rows:
            phrase = row["phrase"]
            emoji = row["emoji"]
            if current.lower() in phrase.lower() or not current:
                display = f"{phrase} → {emoji}"
                if len(display) > 100:
                    display = display[:97] + "..."
                choices.append(app_commands.Choice(name=display, value=phrase))
        return choices[:25]
    except Exception as e:
        logger.debug("Reactbot phrase autocomplete failed: %s", e)
        return []


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class ReactBotGroup(app_commands.Group):
    """Phrase reaction management."""

    def __init__(self, cog: "ReactBotCommands"):
        super().__init__(name="reactbot", description="Phrase reaction management")
        self.cog = cog

    @app_commands.command(name="add", description="Add a phrase reaction (Admin only)")
    @app_commands.describe(
        phrase="Regex pattern to match (case-insensitive)", emoji="Emoji to react with"
    )
    async def add_cmd(self, interaction: discord.Interaction, phrase: str, emoji: str):
        await interaction.response.defer(ephemeral=True)
        try:
            allowed, reason = await self.cog.bot.rate_limiter.check_rate_limit(
                interaction.user.id, interaction.guild_id
            )
            if not allowed:
                await interaction.followup.send(reason, ephemeral=True)
                return
            if not await self.cog._check_admin(interaction, "reactbot add"):
                return

            phrase = InputValidator.validate_phrase_pattern(phrase)
            emoji = InputValidator.validate_emoji(emoji)
            await self.cog.bot.phrase_matcher.validate_pattern(phrase)

            emoji_valid, emoji_error = await self.cog._validate_emoji_accessible(interaction, emoji)
            if not emoji_valid:
                await interaction.followup.send(emoji_error, ephemeral=True)
                return

            async with self.cog.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO phrase_reactions (server_id, phrase, emoji, created_by) VALUES ($1, $2, $3, $4)",
                    interaction.guild_id,
                    phrase,
                    emoji,
                    interaction.user.id,
                )
            self.cog.bot.phrase_matcher.invalidate_cache(interaction.guild_id)
            _invalidate_reactbot_cache(self.cog.bot.cache, interaction.guild_id)
            await interaction.followup.send(f"✅ Added: `{phrase}` → {emoji}", ephemeral=True)
            if self.cog.bot.metrics:
                self.cog.bot.metrics.commands_executed.labels(
                    command_name="reactbot add",
                    server_id=str(interaction.guild_id),
                    status="success",
                ).inc()
        except asyncpg.UniqueViolationError:
            await interaction.followup.send(
                f"❌ This exact phrase + emoji combination already exists: `{phrase}` → {emoji}",
                ephemeral=True,
            )
        except (ValidationError, RegexValidationError) as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception as e:
            logger.error("reactbot add error: %s", e, exc_info=True)
            await interaction.followup.send("❌ Error processing command.", ephemeral=True)

    @app_commands.command(name="list", description="List all phrase reactions")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            cache_key = CACHE_REACTBOT_PHRASES.format(server_id=interaction.guild_id)
            rows = self.cog.bot.cache.get(cache_key) if self.cog.bot.cache else None
            if rows is None:
                async with self.cog.bot.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT phrase, emoji, match_count FROM phrase_reactions WHERE server_id = $1 AND is_active = true ORDER BY match_count DESC",
                        interaction.guild_id,
                    )
                rows = [dict(r) for r in rows]
                if self.cog.bot.cache:
                    self.cog.bot.cache.set(cache_key, rows, ttl=300)
            if not rows:
                await interaction.followup.send("No phrase reactions configured.", ephemeral=True)
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
            await interaction.followup.send("❌ Error fetching reactions.", ephemeral=True)

    @app_commands.command(name="remove", description="Remove a phrase reaction (Admin only)")
    @app_commands.describe(phrase="Select phrase pattern to remove")
    @app_commands.autocomplete(phrase=_reactbot_phrase_autocomplete)
    async def remove_cmd(self, interaction: discord.Interaction, phrase: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self.cog._check_admin(interaction, "reactbot remove"):
                return
            async with self.cog.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE phrase_reactions SET is_active = false WHERE server_id = $1 AND phrase = $2 AND is_active = true",
                    interaction.guild_id,
                    phrase,
                )
            if result == "UPDATE 0":
                await interaction.followup.send(f"❌ Not found: `{phrase}`", ephemeral=True)
                return
            self.cog.bot.phrase_matcher.invalidate_cache(interaction.guild_id)
            _invalidate_reactbot_cache(self.cog.bot.cache, interaction.guild_id)
            await interaction.followup.send(f"✅ Removed: `{phrase}`", ephemeral=True)
        except Exception as e:
            logger.error("reactbot remove error: %s", e, exc_info=True)
            await interaction.followup.send("❌ Error processing command.", ephemeral=True)


class ReactBotCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reactbot_group = ReactBotGroup(self)

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("❌ Admin required.", ephemeral=True)
            return False
        return True

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
        self.bot.tree.add_command(self.reactbot_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.reactbot_group.name)


async def setup(bot):
    await bot.add_cog(ReactBotCommands(bot))
