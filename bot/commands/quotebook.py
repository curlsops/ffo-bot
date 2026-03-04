import logging
import random
import re
from uuid import UUID

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from bot.utils.pagination import ListPaginatedView
from bot.utils.quotebook_channel import get_quotebook_channel_id, set_quotebook_channel
from config.constants import Role

logger = logging.getLogger(__name__)

CACHE_QUOTE_AUTOCOMPLETE = "quotebook_autocomplete:{server_id}"
CACHE_QUOTE_APPROVE_AUTOCOMPLETE = "quotebook_approve_autocomplete:{server_id}"
CACHE_QUOTE_PENDING = "quotebook_pending:{server_id}"
CACHE_QUOTE_APPROVED = "quotebook_approved:{server_id}"


def _invalidate_quotebook_cache(cache, server_id: int) -> None:
    if cache:
        for key in (
            CACHE_QUOTE_AUTOCOMPLETE,
            CACHE_QUOTE_APPROVE_AUTOCOMPLETE,
            CACHE_QUOTE_PENDING,
            CACHE_QUOTE_APPROVED,
        ):
            cache.delete(key.format(server_id=server_id))


def _parse_quotes_from_message(
    message: discord.Message,
) -> list[tuple[str, str | None]]:
    """Extract (quote_text, attribution) pairs from a message.

    Handles formats:
    - "quote text" - @attribution
    - @user "quote text" (Discord mention or literal @name)
    - "quote text" (attribution = message author)
    - Multiple quotes per message
    """
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

    # Pattern 1: "quote" - @attribution or "quote" -@attribution
    for m in re.finditer(r'"([^"]+)"\s*[-—]\s*@?\s*([^\s\n]*)', content):
        add(m.group(1), m.group(2).strip() if m.group(2) else None)

    # Pattern 2: <@id> "quote" or @name "quote"
    for m in re.finditer(r'(?:<@!?(\d+)>|@([^\s"@]+))\s*"([^"]+)"', content):
        quote = m.group(3)
        attr = mention_map.get(m.group(1), m.group(2)) if m.group(1) else m.group(2)
        add(quote, attr)

    # Pattern 3: Standalone "quote" not yet captured (use author)
    for m in re.finditer(r'"([^"]+)"', content):
        add(m.group(1), author_name)

    return results


async def _quote_id_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    try:
        bot = interaction.client
        cache_key = CACHE_QUOTE_AUTOCOMPLETE.format(server_id=interaction.guild_id)
        rows = bot.cache.get(cache_key) if bot.cache else None
        if rows is None:
            async with bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, quote_text, approved
                    FROM quotebook
                    WHERE server_id = $1
                    ORDER BY approved, created_at DESC
                    LIMIT 25
                    """,
                    interaction.guild_id,
                )
            rows = [dict(r) for r in rows]
            if bot.cache:
                bot.cache.set(cache_key, rows, ttl=60)
        choices = []
        for r in rows:
            sid = str(r["id"])
            short = (r["quote_text"][:50] + "…") if len(r["quote_text"]) > 50 else r["quote_text"]
            label = f"{sid[:8]} {short}" + (" ✓" if r["approved"] else " (pending)")
            if not current or current.lower() in sid.lower() or current.lower() in short.lower():
                choices.append(app_commands.Choice(name=label[:100], value=sid))
        return choices[:25]
    except Exception as e:
        logger.debug("Quote ID autocomplete failed: %s", e)
        return []


async def _quote_id_approve_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    try:
        bot = interaction.client
        cache_key = CACHE_QUOTE_APPROVE_AUTOCOMPLETE.format(server_id=interaction.guild_id)
        rows = bot.cache.get(cache_key) if bot.cache else None
        if rows is None:
            async with bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, quote_text
                    FROM quotebook
                    WHERE server_id = $1 AND approved = false
                    ORDER BY created_at DESC
                    LIMIT 25
                    """,
                    interaction.guild_id,
                )
            rows = [dict(r) for r in rows]
            if bot.cache:
                bot.cache.set(cache_key, rows, ttl=60)
        choices = []
        for r in rows:
            sid = str(r["id"])
            short = (r["quote_text"][:50] + "…") if len(r["quote_text"]) > 50 else r["quote_text"]
            label = f"{sid[:8]} {short}"
            if not current or current.lower() in sid.lower() or current.lower() in short.lower():
                choices.append(app_commands.Choice(name=label[:100], value=sid))
        return choices[:25]
    except Exception as e:
        logger.debug("Quote approve autocomplete failed: %s", e)
        return []


@app_commands.guild_only()
class QuoteGroup(app_commands.Group):
    """Quotebook submissions and management."""

    def __init__(self, cog: "QuotebookCommands"):
        super().__init__(name="quote", description="Quotebook submissions and management")
        self.cog = cog

    @app_commands.command(name="submit", description="Submit a quote to the quotebook")
    @app_commands.describe(
        text="The quote text (max 500 chars)",
        attribution="Optional: who said it (e.g. '— Albert Einstein')",
    )
    async def submit_cmd(
        self,
        interaction: discord.Interaction,
        text: str,
        attribution: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return

        text = text.strip()[:500]
        if not text:
            await interaction.followup.send("Quote cannot be empty.", ephemeral=True)
            return

        attr = attribution.strip()[:255] if attribution else None

        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO quotebook (server_id, quote_text, submitter_id, attribution, approved)
                    VALUES ($1, $2, $3, $4, false)
                    """,
                    interaction.guild_id,
                    text,
                    interaction.user.id,
                    attr,
                )
            _invalidate_quotebook_cache(self.cog.bot.cache, interaction.guild_id)
            await interaction.followup.send(
                "Quote submitted! An admin will review it.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("quote submit error: %s", e, exc_info=True)
            await interaction.followup.send("Error submitting quote.", ephemeral=True)

    @app_commands.command(name="list", description="List all quotes (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "quote list"):
            return

        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, quote_text, attribution, approved
                    FROM quotebook
                    WHERE server_id = $1
                    ORDER BY approved, created_at DESC
                    """,
                    interaction.guild_id,
                )
            rows = [dict(r) for r in rows]

            if not rows:
                await interaction.followup.send("No quotes in the book yet.", ephemeral=True)
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
        except Exception as e:
            logger.error("quote list error: %s", e, exc_info=True)
            await interaction.followup.send("Error listing quotes.", ephemeral=True)

    @app_commands.command(name="approve", description="Approve a quote (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(quote_id="Quote ID (from /quote list, pending only)")
    @app_commands.autocomplete(quote_id=_quote_id_approve_autocomplete)
    async def approve_cmd(self, interaction: discord.Interaction, quote_id: str):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "quote approve"):
            return

        try:
            qid = UUID(quote_id)
        except ValueError:
            await interaction.followup.send("Invalid quote ID.", ephemeral=True)
            return

        try:
            row = None
            async with self.cog.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE quotebook SET approved = true, updated_at = NOW()
                    WHERE id = $1 AND server_id = $2 AND approved = false
                    """,
                    qid,
                    interaction.guild_id,
                )

                if "UPDATE 0" in result:
                    await interaction.followup.send(
                        "Quote not found or already approved.", ephemeral=True
                    )
                    return

                row = await conn.fetchrow(
                    "SELECT quote_text, attribution FROM quotebook WHERE id = $1", qid
                )

            _invalidate_quotebook_cache(self.cog.bot.cache, interaction.guild_id)
            await interaction.followup.send("Quote approved!", ephemeral=True)

            if row:
                channel_id = await get_quotebook_channel_id(
                    self.cog.bot.db_pool,
                    interaction.guild_id,
                    self.cog.bot.cache,
                )
                if channel_id:
                    channel = self.cog.bot.get_channel(channel_id)
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
                                "Cannot post quote to channel %s (no permission)", channel_id
                            )
        except Exception as e:
            logger.error("quote approve error: %s", e, exc_info=True)
            await interaction.followup.send("Error approving quote.", ephemeral=True)

    @app_commands.command(name="delete", description="Delete a quote (Admin only)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(quote_id="Quote ID")
    @app_commands.autocomplete(quote_id=_quote_id_autocomplete)
    async def delete_cmd(self, interaction: discord.Interaction, quote_id: str):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "quote delete"):
            return

        try:
            qid = UUID(quote_id)
        except ValueError:
            await interaction.followup.send("Invalid quote ID.", ephemeral=True)
            return

        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM quotebook WHERE id = $1 AND server_id = $2",
                    qid,
                    interaction.guild_id,
                )
            _invalidate_quotebook_cache(self.cog.bot.cache, interaction.guild_id)
            await interaction.followup.send("Quote deleted.", ephemeral=True)
        except Exception as e:
            logger.error("quote delete error: %s", e, exc_info=True)
            await interaction.followup.send("Error deleting quote.", ephemeral=True)

    @app_commands.command(
        name="import",
        description="Import quotes from a channel (Admin only). Reads all messages and extracts quoted text.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to import from (reads full history)",
        auto_approve="Approve imported quotes immediately (default: true)",
    )
    async def import_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        auto_approve: bool = True,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "quote import"):
            return

        if not interaction.guild_id:
            return

        try:
            await self.cog.bot._register_server(interaction.guild)
            await set_quotebook_channel(
                self.cog.bot.db_pool,
                interaction.guild_id,
                channel.id,
                self.cog.bot.cache,
            )

            imported = 0
            skipped = 0

            async with self.cog.bot.db_pool.acquire() as conn:
                async for message in channel.history(limit=None, oldest_first=True):
                    if message.author.bot:
                        continue

                    quotes = _parse_quotes_from_message(message)
                    for quote_text, attribution in quotes:
                        if not quote_text:
                            continue

                        # Avoid duplicates (same quote_text for this server)
                        existing = await conn.fetchval(
                            """
                            SELECT 1 FROM quotebook
                            WHERE server_id = $1 AND quote_text = $2
                            LIMIT 1
                            """,
                            interaction.guild_id,
                            quote_text,
                        )
                        if existing:
                            skipped += 1
                            continue

                        await conn.execute(
                            """
                            INSERT INTO quotebook (server_id, quote_text, submitter_id, attribution, approved)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            interaction.guild_id,
                            quote_text,
                            message.author.id,
                            attribution,
                            auto_approve,
                        )
                        imported += 1

            _invalidate_quotebook_cache(self.cog.bot.cache, interaction.guild_id)

            msg = f"Imported **{imported}** quotes from {channel.mention}. Approved quotes will now be posted there."
            if skipped:
                msg += f" Skipped {skipped} duplicates."
            await interaction.followup.send(msg, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to read that channel.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("quote import error: %s", e, exc_info=True)
            await interaction.followup.send(
                f"Error importing: {e}",
                ephemeral=True,
            )

    @app_commands.command(name="random", description="Post a random approved quote")
    async def random_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            cache_key = CACHE_QUOTE_APPROVED.format(server_id=interaction.guild_id)
            rows = self.cog.bot.cache.get(cache_key) if self.cog.bot.cache else None
            if rows is None:
                async with self.cog.bot.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT quote_text, attribution
                        FROM quotebook
                        WHERE server_id = $1 AND approved = true
                        """,
                        interaction.guild_id,
                    )
                rows = [dict(r) for r in rows]
                if self.cog.bot.cache:
                    self.cog.bot.cache.set(cache_key, rows, ttl=60)

            if not rows:
                await interaction.followup.send("No quotes in the book yet.", ephemeral=True)
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
        except Exception as e:
            logger.error("quote random error: %s", e, exc_info=True)
            await interaction.followup.send("Error fetching quote.", ephemeral=True)


class QuotebookCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.quote_group = QuoteGroup(self)

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("Admin required.", ephemeral=True)
            return False
        return True

    async def cog_load(self):
        self.bot.tree.add_command(self.quote_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.quote_group.name)


async def setup(bot):
    await bot.add_cog(QuotebookCommands(bot))
