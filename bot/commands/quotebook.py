import logging
import random
import re
from uuid import UUID

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import execute_command, require_admin, send_error
from bot.services.quotebook_service import (
    CACHE_QUOTE_APPROVE_AUTOCOMPLETE,
    CACHE_QUOTE_AUTOCOMPLETE,
    QuotebookService,
)
from bot.utils.autocomplete import cached_autocomplete
from bot.utils.channel_config import get_quotebook_channel_id, set_quotebook_channel
from bot.utils.discord_helpers import get_or_fetch_channel
from bot.utils.log_context import log_command_start
from bot.utils.pagination import ListPaginatedView
from bot.utils.telemetry import trace_span
from config.constants import Constants

logger = logging.getLogger(__name__)


def _parse_quotes_from_message(
    message: discord.Message,
) -> list[tuple[str, str | None]]:
    content = message.content or ""
    if not content.strip():
        return []

    author_name = message.author.display_name or str(message.author)
    mention_map = {str(u.id): u.display_name or str(u) for u in message.mentions}

    results: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    def add(quote: str, attr: str | None) -> None:
        quote = quote.strip()[:500]
        if quote and quote not in seen:
            seen.add(quote)
            results.append((quote, (attr or "").strip()[:255] or None))

    for m in re.finditer(r'"([^"]+)"\s*[-—]\s*@?\s*([^\s\n]*)', content):
        add(m.group(1), m.group(2).strip() if m.group(2) else None)

    for m in re.finditer(r'(?:<@!?(\d+)>|@([^\s"@]+))\s*"([^"]+)"', content):
        quote = m.group(3)
        attr = mention_map.get(m.group(1), m.group(2)) if m.group(1) else m.group(2)
        add(quote, attr)

    for m in re.finditer(r'"([^"]+)"', content):
        add(m.group(1), author_name)

    return results


async def _fetch_quote_ids(pool, guild_id: int):
    return await QuotebookService(pool).list_quote_ids(guild_id)


async def _fetch_quote_approve_ids(pool, guild_id: int):
    return await QuotebookService(pool).list_pending_quote_ids(guild_id)


def _rows_to_choices(
    rows: list[dict], current: str, include_approved: bool = False
) -> list[app_commands.Choice[str]]:
    choices = []
    for r in rows:
        sid = str(r["id"])
        short = (r["quote_text"][:50] + "…") if len(r["quote_text"]) > 50 else r["quote_text"]
        label = f"{sid[:8]} {short}"
        if include_approved:
            label += " ✓" if r.get("approved") else " (pending)"
        if not current or current.lower() in sid.lower() or current.lower() in short.lower():
            choices.append(app_commands.Choice(name=label[:100], value=sid))
    return choices


def _rows_to_choices_with_approved(
    rows: list[dict], current: str
) -> list[app_commands.Choice[str]]:
    return _rows_to_choices(rows, current, include_approved=True)


async def _quote_id_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return await cached_autocomplete(
        interaction,
        current,
        CACHE_QUOTE_AUTOCOMPLETE,
        _fetch_quote_ids,
        _rows_to_choices_with_approved,
        ttl=Constants.CACHE_TTL,
        log_prefix="Quote ID",
    )


async def _quote_id_approve_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return await cached_autocomplete(
        interaction,
        current,
        CACHE_QUOTE_APPROVE_AUTOCOMPLETE,
        _fetch_quote_approve_ids,
        _rows_to_choices,
        ttl=Constants.CACHE_TTL,
        log_prefix="Quote approve",
    )


async def _quote_list_check(self: "QuoteGroup", interaction: discord.Interaction) -> bool:
    return await require_admin(interaction, "quote list", self.cog.bot)


async def _quote_approve_check(
    self: "QuoteGroup", interaction: discord.Interaction, quote_id: str
) -> bool:
    return await require_admin(interaction, "quote approve", self.cog.bot)


async def _quote_delete_check(
    self: "QuoteGroup", interaction: discord.Interaction, quote_id: str
) -> bool:
    return await require_admin(interaction, "quote delete", self.cog.bot)


async def _quote_import_check(
    self: "QuoteGroup",
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    auto_approve: bool = True,
) -> bool:
    return await require_admin(interaction, "quote import", self.cog.bot)


@app_commands.guild_only()
class QuoteGroup(app_commands.Group):
    def __init__(self, cog: "QuotebookCommands"):
        super().__init__(name="quote", description="Quotebook submissions and management")
        self.cog = cog

    @app_commands.command(name="submit", description="Submit a quote to the quotebook")
    @app_commands.describe(
        text="The quote text (max 500 chars)",
        attribution="Optional: who said it (e.g. '— Albert Einstein')",
    )
    @execute_command(
        error_message="Error submitting quote.",
        logger=logger,
        log_prefix="quote submit error",
    )
    async def submit_cmd(
        self,
        interaction: discord.Interaction,
        text: str,
        attribution: str | None = None,
    ):
        log_command_start(logger, "quotebook", "quote submit", interaction)
        if not interaction.guild_id:
            return

        text = text.strip()[:500]
        if not text:
            await send_error(interaction, "Quote cannot be empty.")
            return

        attr = attribution.strip()[:255] if attribution else None

        quote_id = await self.cog.service.submit_quote(
            interaction.guild_id, text, interaction.user.id, attr, cache=self.cog.bot.cache
        )
        if self.cog.bot.notifier and quote_id:
            await self.cog.bot.notifier.notify_quotebook_submitted(
                interaction.guild_id, text, interaction.user.id, quote_id
            )
        await interaction.followup.send(
            "Quote submitted! An admin will review it.",
            ephemeral=True,
        )

    @app_commands.command(name="list", description="List all quotes (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @execute_command(
        permission_check=_quote_list_check,
        error_message="Error listing quotes.",
        logger=logger,
        log_prefix="quote list error",
    )
    async def list_cmd(self, interaction: discord.Interaction):
        log_command_start(logger, "quotebook", "quote list", interaction)

        rows = await self.cog.service.list_all_quotes(interaction.guild_id)

        if not rows:
            await send_error(interaction, "No quotes in the book yet.")
            return

        def fmt(r):
            short = r["quote_text"][:80] + "…" if len(r["quote_text"]) > 80 else r["quote_text"]
            attr = f" — {r['attribution']}" if r["attribution"] else ""
            status = " ✓" if r["approved"] else " (pending)"
            return f"`{str(r['id'])[:8]}` {short}{attr}{status}"

        view = ListPaginatedView(rows, "**Quotebook:**", fmt)
        await interaction.followup.send(
            view._format_page(),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="approve", description="Approve a quote (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(quote_id="Quote ID (from /quote list, pending only)")
    @app_commands.autocomplete(quote_id=_quote_id_approve_autocomplete)
    @execute_command(
        permission_check=_quote_approve_check,
        error_message="Error approving quote.",
        logger=logger,
        log_prefix="quote approve error",
    )
    async def approve_cmd(self, interaction: discord.Interaction, quote_id: str):
        log_command_start(logger, "quotebook", "quote approve", interaction)

        try:
            qid = UUID(quote_id)
        except ValueError:
            await send_error(interaction, "Invalid quote ID.")
            return

        with trace_span(
            "quotebook.approve",
            attributes={
                "guild_id": str(interaction.guild_id),
                "quotebook.quote_id": str(qid),
            },
        ):
            row = await self.cog.service.approve_quote(
                qid, interaction.guild_id, cache=self.cog.bot.cache
            )
            if row is None:
                await send_error(interaction, "Quote not found or already approved.")
                return

            await interaction.followup.send("Quote approved!", ephemeral=True)

            channel_id = await get_quotebook_channel_id(
                self.cog.bot.db_pool,
                interaction.guild_id,
                self.cog.bot.cache,
            )
            if channel_id:
                channel = await get_or_fetch_channel(self.cog.bot, channel_id)
                if channel is None:
                    logger.warning("Could not fetch quotebook channel %s", channel_id)
                if channel:
                    text = row["quote_text"]
                    if row["attribution"]:
                        text += f"\n— {row['attribution']}"
                    embed = discord.Embed(
                        description=text[:4096],
                        color=discord.Color.blue(),
                    )
                    embed.set_footer(text="📖 Quotebook")
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        logger.warning(
                            "Cannot post quote to channel %s (no permission)",
                            channel_id,
                        )

    @app_commands.command(name="delete", description="Delete a quote (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(quote_id="Quote ID")
    @app_commands.autocomplete(quote_id=_quote_id_autocomplete)
    @execute_command(
        permission_check=_quote_delete_check,
        error_message="Error deleting quote.",
        logger=logger,
        log_prefix="quote delete error",
    )
    async def delete_cmd(self, interaction: discord.Interaction, quote_id: str):
        log_command_start(logger, "quotebook", "quote delete", interaction)

        try:
            qid = UUID(quote_id)
        except ValueError:
            await send_error(interaction, "Invalid quote ID.")
            return

        await self.cog.service.delete_quote(qid, interaction.guild_id, cache=self.cog.bot.cache)
        await interaction.followup.send("Quote deleted.", ephemeral=True)

    @app_commands.command(
        name="import",
        description="Import quotes from a channel (Admin only). Reads all messages and extracts quoted text.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to import from (reads full history)",
        auto_approve="Approve imported quotes immediately (default: true)",
    )
    @execute_command(
        permission_check=_quote_import_check,
        error_message="Error importing quotes.",
        logger=logger,
        log_prefix="quote import error",
    )
    async def import_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        auto_approve: bool = True,
    ):
        log_command_start(logger, "quotebook", "quote import", interaction)

        try:
            with trace_span(
                "quotebook.import",
                attributes={
                    "guild_id": str(interaction.guild_id),
                    "discord.channel_id": str(channel.id),
                    "quotebook.auto_approve": auto_approve,
                },
            ):
                await self.cog.bot._register_server(interaction.guild)
                await set_quotebook_channel(
                    self.cog.bot.db_pool,
                    interaction.guild_id,
                    channel.id,
                    self.cog.bot.cache,
                )

                collected: list[tuple[str, str | None, int]] = []
                messages_scanned = 0
                with trace_span(
                    "quotebook.import_scan_history",
                ) as scan_span:
                    async for message in channel.history(limit=None, oldest_first=True):
                        messages_scanned += 1
                        if message.author.bot:
                            continue
                        for quote_text, attribution in _parse_quotes_from_message(message):
                            if quote_text:
                                collected.append((quote_text, attribution, message.author.id))

                    scan_span.set_attribute("quotebook.messages_scanned", messages_scanned)
                    scan_span.set_attribute("quotebook.quotes_found", len(collected))

                inserted = await self.cog.service.import_new_quotes(
                    interaction.guild_id, collected, auto_approve, cache=self.cog.bot.cache
                )
                imported = len(inserted)
                skipped = len(collected) - imported

                if auto_approve:
                    for quote_text, attribution in inserted:
                        text = f"{quote_text}\n— {attribution}" if attribution else quote_text
                        embed = discord.Embed(
                            description=text[:4096],
                            color=discord.Color.blue(),
                        )
                        embed.set_footer(text="📖 Quotebook (imported)")
                        try:
                            await channel.send(embed=embed)
                        except discord.Forbidden:
                            logger.warning("Cannot post imported quote to channel %s", channel.id)

                msg = f"Imported **{imported}** quotes from {channel.mention}."
                if auto_approve and imported:
                    msg += " New approved quotes have been posted."
                if skipped:
                    msg += f" Skipped {skipped} duplicates."
                await interaction.followup.send(msg, ephemeral=True)

        except discord.Forbidden:
            await send_error(interaction, "I don't have permission to read that channel.")
        except Exception as e:
            logger.error("quote import error: %s", e, exc_info=True)
            await send_error(interaction, f"Error importing: {e}")

    @app_commands.command(name="random", description="Post a random approved quote")
    @execute_command(
        defer_ephemeral=False,
        error_message="Error fetching quote.",
        logger=logger,
        log_prefix="quote random error",
    )
    async def random_cmd(self, interaction: discord.Interaction):
        log_command_start(logger, "quotebook", "quote random", interaction)

        rows = await self.cog.service.fetch_approved_quotes(
            interaction.guild_id, cache=self.cog.bot.cache
        )

        if not rows:
            await send_error(interaction, "No quotes in the book yet.")
            return

        r = random.choice(rows)
        text = r["quote_text"]
        if r["attribution"]:
            text += f"\n— {r['attribution']}"

        embed = discord.Embed(
            description=text[:4096],
            color=discord.Color.blue(),
        )
        embed.set_footer(text="📖 Quotebook")
        await interaction.followup.send(embed=embed, ephemeral=False)


class QuotebookCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = QuotebookService(bot.db_pool)
        self.quote_group = QuoteGroup(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.quote_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.quote_group.name)


async def setup(bot):
    await bot.add_cog(QuotebookCommands(bot))
