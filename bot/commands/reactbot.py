"""Reaction bot configuration commands."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.regex_validator import RegexValidationError
from bot.utils.validation import InputValidator, ValidationError
from config.constants import Role

logger = logging.getLogger(__name__)


class ReactBotCommands(commands.Cog):
    """Reaction bot configuration commands."""

    def __init__(self, bot):
        """
        Initialize reactbot commands.

        Args:
            bot: Bot instance
        """
        self.bot = bot

    @app_commands.command(name="reactbot_add", description="Add a phrase reaction (Admin only)")
    @app_commands.describe(
        phrase="Regex pattern to match (case-insensitive)", emoji="Emoji to react with"
    )
    async def reactbot_add(self, interaction: discord.Interaction, phrase: str, emoji: str):
        """
        Add phrase reaction.

        Args:
            interaction: Discord interaction
            phrase: Regex pattern
            emoji: Emoji to add
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Check rate limit
            allowed, reason = await self.bot.rate_limiter.check_rate_limit(
                interaction.user.id, interaction.guild_id
            )
            if not allowed:
                await interaction.followup.send(reason, ephemeral=True)
                return

            # Check permissions
            ctx = PermissionContext(
                server_id=interaction.guild_id,
                user_id=interaction.user.id,
                command_name="reactbot_add",
            )

            has_permission = await self.bot.permission_checker.check_role(ctx, Role.ADMIN)
            if not has_permission:
                await interaction.followup.send(
                    "❌ You need Admin role to use this command.", ephemeral=True
                )
                return

            # Validate inputs
            phrase = InputValidator.validate_phrase_pattern(phrase)
            emoji = InputValidator.validate_emoji(emoji)

            # Validate regex for ReDoS
            await self.bot.phrase_matcher.validate_pattern(phrase)

            # Store in database
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO phrase_reactions
                    (server_id, phrase, emoji, created_by)
                    VALUES ($1, $2, $3, $4)
                    """,
                    interaction.guild_id,
                    phrase,
                    emoji,
                    interaction.user.id,
                )

            # Invalidate cache
            self.bot.phrase_matcher.invalidate_cache(interaction.guild_id)

            # Audit log
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log
                    (server_id, user_id, action, target_type, target_id, details)
                    VALUES ($1, $2, 'phrase_added', 'phrase', $3, $4)
                    """,
                    interaction.guild_id,
                    interaction.user.id,
                    phrase,
                    {"emoji": emoji},
                )

            await interaction.followup.send(
                f"✅ Successfully added phrase reaction: `{phrase}` → {emoji}", ephemeral=True
            )

            # Update metrics
            if self.bot.metrics:
                self.bot.metrics.commands_executed.labels(
                    command_name="reactbot_add",
                    server_id=str(interaction.guild_id),
                    status="success",
                ).inc()

        except ValidationError as e:
            await interaction.followup.send(f"❌ Invalid input: {e}", ephemeral=True)
        except RegexValidationError as e:
            await interaction.followup.send(f"❌ Invalid regex pattern: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in reactbot_add command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while processing your command.", ephemeral=True
            )
            if self.bot.metrics:
                self.bot.metrics.commands_executed.labels(
                    command_name="reactbot_add", server_id=str(interaction.guild_id), status="error"
                ).inc()

    @app_commands.command(name="reactbot_list", description="List all phrase reactions")
    async def reactbot_list(self, interaction: discord.Interaction):
        """
        List all phrase reactions for the server.

        Args:
            interaction: Discord interaction
        """
        await interaction.response.defer(ephemeral=True)

        try:
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT phrase, emoji, match_count, last_matched_at
                    FROM phrase_reactions
                    WHERE server_id = $1 AND is_active = true
                    ORDER BY match_count DESC
                    """,
                    interaction.guild_id,
                )

            if not rows:
                await interaction.followup.send(
                    "No phrase reactions configured for this server.", ephemeral=True
                )
                return

            # Build response
            response = "**Phrase Reactions:**\n\n"
            for row in rows[:25]:  # Limit to 25 to avoid message length issues
                match_info = f"(Matched {row['match_count']} times)"
                response += f"• `{row['phrase']}` → {row['emoji']} {match_info}\n"

            if len(rows) > 25:
                response += f"\n*... and {len(rows) - 25} more*"

            await interaction.followup.send(response, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in reactbot_list command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching phrase reactions.", ephemeral=True
            )

    @app_commands.command(
        name="reactbot_remove", description="Remove a phrase reaction (Admin only)"
    )
    @app_commands.describe(phrase="Exact phrase pattern to remove")
    async def reactbot_remove(self, interaction: discord.Interaction, phrase: str):
        """
        Remove phrase reaction.

        Args:
            interaction: Discord interaction
            phrase: Phrase pattern to remove
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Check permissions
            ctx = PermissionContext(
                server_id=interaction.guild_id,
                user_id=interaction.user.id,
                command_name="reactbot_remove",
            )

            has_permission = await self.bot.permission_checker.check_role(ctx, Role.ADMIN)
            if not has_permission:
                await interaction.followup.send(
                    "❌ You need Admin role to use this command.", ephemeral=True
                )
                return

            # Remove from database
            async with self.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE phrase_reactions
                    SET is_active = false
                    WHERE server_id = $1 AND phrase = $2 AND is_active = true
                    """,
                    interaction.guild_id,
                    phrase,
                )

            # Check if anything was removed
            if result == "UPDATE 0":
                await interaction.followup.send(
                    f"❌ No active phrase reaction found for: `{phrase}`", ephemeral=True
                )
                return

            # Invalidate cache
            self.bot.phrase_matcher.invalidate_cache(interaction.guild_id)

            await interaction.followup.send(
                f"✅ Successfully removed phrase reaction: `{phrase}`", ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in reactbot_remove command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while processing your command.", ephemeral=True
            )


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(ReactBotCommands(bot))
