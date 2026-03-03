import logging

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.regex_validator import RegexValidationError
from bot.utils.validation import InputValidator, ValidationError
from config.constants import Role

logger = logging.getLogger(__name__)


async def _reactbot_phrase_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    try:
        bot = interaction.client
        async with bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT phrase, emoji FROM phrase_reactions
                   WHERE server_id = $1 AND is_active = true
                   ORDER BY match_count DESC LIMIT 25""",
                interaction.guild_id,
            )
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
    except Exception:
        return []


class ReactBotCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    @app_commands.command(
        name="reactbot_add",
        description="Add a phrase reaction (Admin only)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        phrase="Regex pattern to match (case-insensitive)", emoji="Emoji to react with"
    )
    async def reactbot_add(self, interaction: discord.Interaction, phrase: str, emoji: str):
        await interaction.response.defer(ephemeral=True)
        try:
            allowed, reason = await self.bot.rate_limiter.check_rate_limit(
                interaction.user.id, interaction.guild_id
            )
            if not allowed:
                await interaction.followup.send(reason, ephemeral=True)
                return
            if not await self._check_admin(interaction, "reactbot_add"):
                return

            phrase = InputValidator.validate_phrase_pattern(phrase)
            emoji = InputValidator.validate_emoji(emoji)
            await self.bot.phrase_matcher.validate_pattern(phrase)

            emoji_valid, emoji_error = await self._validate_emoji_accessible(interaction, emoji)
            if not emoji_valid:
                await interaction.followup.send(emoji_error, ephemeral=True)
                return

            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO phrase_reactions (server_id, phrase, emoji, created_by) VALUES ($1, $2, $3, $4)",
                    interaction.guild_id,
                    phrase,
                    emoji,
                    interaction.user.id,
                )
            self.bot.phrase_matcher.invalidate_cache(interaction.guild_id)
            await interaction.followup.send(f"✅ Added: `{phrase}` → {emoji}", ephemeral=True)
            if self.bot.metrics:
                self.bot.metrics.commands_executed.labels(
                    command_name="reactbot_add",
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
            logger.error(f"reactbot_add error: {e}", exc_info=True)
            await interaction.followup.send("❌ Error processing command.", ephemeral=True)

    @app_commands.command(
        name="reactbot_list",
        description="List all phrase reactions",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def reactbot_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT phrase, emoji, match_count FROM phrase_reactions WHERE server_id = $1 AND is_active = true ORDER BY match_count DESC",
                    interaction.guild_id,
                )
            if not rows:
                await interaction.followup.send("No phrase reactions configured.", ephemeral=True)
                return
            lines = [
                f"• `{r['phrase']}` → {r['emoji']} ({r['match_count']} matches)" for r in rows[:25]
            ]
            response = "**Phrase Reactions:**\n\n" + "\n".join(lines)
            if len(rows) > 25:
                response += f"\n*... and {len(rows) - 25} more*"
            await interaction.followup.send(response, ephemeral=True)
        except Exception as e:
            logger.error(f"reactbot_list error: {e}", exc_info=True)
            await interaction.followup.send("❌ Error fetching reactions.", ephemeral=True)

    @app_commands.command(
        name="reactbot_remove",
        description="Remove a phrase reaction (Admin only)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(phrase="Select phrase pattern to remove")
    @app_commands.autocomplete(phrase=_reactbot_phrase_autocomplete)
    async def reactbot_remove(self, interaction: discord.Interaction, phrase: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self._check_admin(interaction, "reactbot_remove"):
                return
            async with self.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE phrase_reactions SET is_active = false WHERE server_id = $1 AND phrase = $2 AND is_active = true",
                    interaction.guild_id,
                    phrase,
                )
            if result == "UPDATE 0":
                await interaction.followup.send(f"❌ Not found: `{phrase}`", ephemeral=True)
                return
            self.bot.phrase_matcher.invalidate_cache(interaction.guild_id)
            await interaction.followup.send(f"✅ Removed: `{phrase}`", ephemeral=True)
        except Exception as e:
            logger.error(f"reactbot_remove error: {e}", exc_info=True)
            await interaction.followup.send("❌ Error processing command.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ReactBotCommands(bot))
