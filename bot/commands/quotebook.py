import logging
import random
from uuid import UUID

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role

logger = logging.getLogger(__name__)

CACHE_QUOTE_AUTOCOMPLETE = "quotebook_autocomplete:{server_id}"
CACHE_QUOTE_PENDING = "quotebook_pending:{server_id}"
CACHE_QUOTE_APPROVED = "quotebook_approved:{server_id}"


def _invalidate_quotebook_cache(cache, server_id: int) -> None:
    if cache:
        for key in (CACHE_QUOTE_AUTOCOMPLETE, CACHE_QUOTE_PENDING, CACHE_QUOTE_APPROVED):
            cache.delete(key.format(server_id=server_id))


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
    except Exception:
        return []


class QuotebookCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id, user_id=interaction.user.id, command_name=cmd
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("Admin required.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="quote_submit", description="Submit a quote to the quotebook")
    @app_commands.guild_only()
    @app_commands.describe(
        text="The quote text (max 500 chars)",
        attribution="Optional: who said it (e.g. '— Albert Einstein')",
    )
    async def quote_submit(
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
            async with self.bot.db_pool.acquire() as conn:
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
            _invalidate_quotebook_cache(self.bot.cache, interaction.guild_id)
            await interaction.followup.send(
                "Quote submitted! An admin will review it.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("quote_submit error: %s", e, exc_info=True)
            await interaction.followup.send("Error submitting quote.", ephemeral=True)

    @app_commands.command(name="quote_list", description="List pending quotes (Admin only)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def quote_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_admin(interaction, "quote_list"):
            return

        try:
            cache_key = CACHE_QUOTE_PENDING.format(server_id=interaction.guild_id)
            rows = self.bot.cache.get(cache_key) if self.bot.cache else None
            if rows is None:
                async with self.bot.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, quote_text, submitter_id, attribution, created_at
                        FROM quotebook
                        WHERE server_id = $1 AND approved = false
                        ORDER BY created_at DESC
                        LIMIT 15
                        """,
                        interaction.guild_id,
                    )
                rows = [dict(r) for r in rows]
                if self.bot.cache:
                    self.bot.cache.set(cache_key, rows, ttl=60)

            if not rows:
                await interaction.followup.send("No pending quotes.", ephemeral=True)
                return

            lines = []
            for r in rows:
                short = r["quote_text"][:80] + "…" if len(r["quote_text"]) > 80 else r["quote_text"]
                attr = f" — {r['attribution']}" if r["attribution"] else ""
                lines.append(f"`{str(r['id'])[:8]}` {short}{attr}")

            await interaction.followup.send(
                "**Pending quotes:**\n" + "\n".join(lines),
                ephemeral=True,
            )
        except Exception as e:
            logger.error("quote_list error: %s", e, exc_info=True)
            await interaction.followup.send("Error listing quotes.", ephemeral=True)

    @app_commands.command(name="quote_approve", description="Approve a quote (Admin only)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(quote_id="Quote ID (from /quote_list)")
    @app_commands.autocomplete(quote_id=_quote_id_autocomplete)
    async def quote_approve(self, interaction: discord.Interaction, quote_id: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_admin(interaction, "quote_approve"):
            return

        try:
            qid = UUID(quote_id)
        except ValueError:
            await interaction.followup.send("Invalid quote ID.", ephemeral=True)
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
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

            _invalidate_quotebook_cache(self.bot.cache, interaction.guild_id)
            await interaction.followup.send("Quote approved!", ephemeral=True)
        except Exception as e:
            logger.error("quote_approve error: %s", e, exc_info=True)
            await interaction.followup.send("Error approving quote.", ephemeral=True)

    @app_commands.command(name="quote_delete", description="Delete a quote (Admin only)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(quote_id="Quote ID")
    @app_commands.autocomplete(quote_id=_quote_id_autocomplete)
    async def quote_delete(self, interaction: discord.Interaction, quote_id: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_admin(interaction, "quote_delete"):
            return

        try:
            qid = UUID(quote_id)
        except ValueError:
            await interaction.followup.send("Invalid quote ID.", ephemeral=True)
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM quotebook WHERE id = $1 AND server_id = $2",
                    qid,
                    interaction.guild_id,
                )
            _invalidate_quotebook_cache(self.bot.cache, interaction.guild_id)
            await interaction.followup.send("Quote deleted.", ephemeral=True)
        except Exception as e:
            logger.error("quote_delete error: %s", e, exc_info=True)
            await interaction.followup.send("Error deleting quote.", ephemeral=True)

    @app_commands.command(name="quote_random", description="Post a random approved quote")
    @app_commands.guild_only()
    async def quote_random(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            cache_key = CACHE_QUOTE_APPROVED.format(server_id=interaction.guild_id)
            rows = self.bot.cache.get(cache_key) if self.bot.cache else None
            if rows is None:
                async with self.bot.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT quote_text, attribution
                        FROM quotebook
                        WHERE server_id = $1 AND approved = true
                        """,
                        interaction.guild_id,
                    )
                rows = [dict(r) for r in rows]
                if self.bot.cache:
                    self.bot.cache.set(cache_key, rows, ttl=60)

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
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error("quote_random error: %s", e, exc_info=True)
            await interaction.followup.send("Error fetching quote.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(QuotebookCommands(bot))
