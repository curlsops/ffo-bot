"""FAQ commands: list topics, show Q&A. Admin: add, edit, delete."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.permissions import PermissionContext
from config.constants import Role

logger = logging.getLogger(__name__)

MAX_ANSWER_LEN = 1024
MAX_QUESTION_LEN = 200
MAX_TOPIC_LEN = 100
MAX_TOPICS = 25

CACHE_FAQ_TOPICS = "faq_topics:{server_id}"
CACHE_FAQ_ENTRY = "faq_entry:{server_id}:{topic}"


def _invalidate_faq_cache(cache, server_id: int, topic: str | None = None) -> None:
    if cache:
        cache.delete(CACHE_FAQ_TOPICS.format(server_id=server_id))
        if topic:
            cache.delete(CACHE_FAQ_ENTRY.format(server_id=server_id, topic=topic))


async def _faq_topic_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []
    try:
        bot = interaction.client
        cache_key = CACHE_FAQ_TOPICS.format(server_id=interaction.guild_id)
        rows = bot.cache.get(cache_key) if bot.cache else None
        if rows is None:
            async with bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT topic FROM faq_entries
                    WHERE server_id = $1
                    ORDER BY sort_order, topic
                    """,
                    interaction.guild_id,
                )
            rows = [dict(r) for r in rows]
            if bot.cache:
                bot.cache.set(cache_key, rows, ttl=300)
        choices = [
            app_commands.Choice(name=r["topic"], value=r["topic"])
            for r in rows
            if not current or current.lower() in r["topic"].lower()
        ]
        return choices[:25]
    except Exception:
        return []


class FAQCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        ctx = PermissionContext(
            server_id=interaction.guild_id or 0,
            user_id=interaction.user.id,
            command_name=cmd,
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("Admin required.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="faq", description="List FAQ topics or show a specific topic")
    @app_commands.guild_only()
    @app_commands.describe(topic="Topic to look up (leave empty to list all)")
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def faq(
        self,
        interaction: discord.Interaction,
        topic: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return

        try:
            topic_key = topic.strip().lower() if topic else None
            if topic_key:
                cache_key = CACHE_FAQ_ENTRY.format(server_id=interaction.guild_id, topic=topic_key)
                row = self.bot.cache.get(cache_key) if self.bot.cache else None
                if row is None:
                    async with self.bot.db_pool.acquire() as conn:
                        row = await conn.fetchrow(
                            """
                            SELECT question, answer FROM faq_entries
                            WHERE server_id = $1 AND topic = $2
                            """,
                            interaction.guild_id,
                            topic_key,
                        )
                    if row and self.bot.cache:
                        self.bot.cache.set(cache_key, dict(row), ttl=300)
                if not row:
                    await interaction.followup.send(
                        f"No FAQ entry for **{topic}**. Use `/faq` with no topic to list.",
                        ephemeral=True,
                    )
                    return
                embed = discord.Embed(
                    title=row["question"][:256],
                    description=row["answer"][:MAX_ANSWER_LEN],
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"FAQ • {topic}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                cache_key = CACHE_FAQ_TOPICS.format(server_id=interaction.guild_id)
                rows = self.bot.cache.get(cache_key) if self.bot.cache else None
                if rows is None:
                    async with self.bot.db_pool.acquire() as conn:
                        rows = await conn.fetch(
                            """
                            SELECT topic FROM faq_entries
                            WHERE server_id = $1
                            ORDER BY sort_order, topic
                            """,
                            interaction.guild_id,
                        )
                    if self.bot.cache:
                        self.bot.cache.set(cache_key, [dict(r) for r in rows], ttl=300)
                if not rows:
                    await interaction.followup.send(
                        "No FAQ entries yet. Admins can add them with `/faq_add`.",
                        ephemeral=True,
                    )
                    return
                lines = [f"• **{r['topic']}**" for r in rows]
                embed = discord.Embed(
                    title="FAQ Topics",
                    description="\n".join(lines)[:4096],
                    color=discord.Color.blue(),
                )
                embed.set_footer(text="Use /faq topic:<name> to view")
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error("faq error: %s", e, exc_info=True)
            await interaction.followup.send("Error fetching FAQ.", ephemeral=True)

    @app_commands.command(name="faq_add", description="Add a FAQ entry (Admin)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        topic="Topic/slug (e.g. whitelist, rules)",
        question="The question or topic title",
        answer="The answer (max 1024 chars)",
    )
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def faq_add(
        self,
        interaction: discord.Interaction,
        topic: str,
        question: str,
        answer: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id or not await self._check_admin(interaction, "faq_add"):
            return

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        question = question.strip()[:MAX_QUESTION_LEN]
        answer = answer.strip()[:MAX_ANSWER_LEN]

        if not topic or not question or not answer:
            await interaction.followup.send(
                "Topic, question, and answer are required.",
                ephemeral=True,
            )
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM faq_entries WHERE server_id = $1",
                    interaction.guild_id,
                )
                if count and count >= MAX_TOPICS:
                    await interaction.followup.send(
                        f"Maximum {MAX_TOPICS} FAQ topics per server.",
                        ephemeral=True,
                    )
                    return

                await conn.execute(
                    """
                    INSERT INTO faq_entries (server_id, topic, question, answer, sort_order)
                    VALUES ($1, $2, $3, $4, COALESCE(
                        (SELECT MAX(sort_order) + 1 FROM faq_entries WHERE server_id = $1), 0
                    ))
                    ON CONFLICT (server_id, topic) DO UPDATE
                    SET question = EXCLUDED.question, answer = EXCLUDED.answer, updated_at = NOW()
                    """,
                    interaction.guild_id,
                    topic,
                    question,
                    answer,
                )
            _invalidate_faq_cache(self.bot.cache, interaction.guild_id, topic)
            await interaction.followup.send(f"FAQ **{topic}** added/updated.", ephemeral=True)
        except Exception as e:
            logger.error("faq_add error: %s", e, exc_info=True)
            await interaction.followup.send("Error adding FAQ.", ephemeral=True)

    @app_commands.command(name="faq_edit", description="Edit a FAQ entry (Admin)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        topic="Topic to edit",
        question="New question (leave empty to keep)",
        answer="New answer (leave empty to keep)",
    )
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def faq_edit(
        self,
        interaction: discord.Interaction,
        topic: str,
        question: str | None = None,
        answer: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id or not await self._check_admin(interaction, "faq_edit"):
            return

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        if not topic:
            await interaction.followup.send("Topic is required.", ephemeral=True)
            return

        if not question and not answer:
            await interaction.followup.send(
                "Provide at least question or answer to update.",
                ephemeral=True,
            )
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT question, answer FROM faq_entries WHERE server_id = $1 AND topic = $2",
                    interaction.guild_id,
                    topic,
                )
                if not row:
                    await interaction.followup.send(
                        f"No FAQ entry for **{topic}**.", ephemeral=True
                    )
                    return

                new_q = question.strip()[:MAX_QUESTION_LEN] if question else row["question"]
                new_a = answer.strip()[:MAX_ANSWER_LEN] if answer else row["answer"]

                await conn.execute(
                    """
                    UPDATE faq_entries
                    SET question = $1, answer = $2, updated_at = NOW()
                    WHERE server_id = $3 AND topic = $4
                    """,
                    new_q,
                    new_a,
                    interaction.guild_id,
                    topic,
                )
            _invalidate_faq_cache(self.bot.cache, interaction.guild_id, topic)
            await interaction.followup.send(f"FAQ **{topic}** updated.", ephemeral=True)
        except Exception as e:
            logger.error("faq_edit error: %s", e, exc_info=True)
            await interaction.followup.send("Error editing FAQ.", ephemeral=True)

    @app_commands.command(name="faq_delete", description="Delete a FAQ entry (Admin)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(topic="Topic to delete")
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def faq_delete(
        self,
        interaction: discord.Interaction,
        topic: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id or not await self._check_admin(interaction, "faq_delete"):
            return

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        if not topic:
            await interaction.followup.send("Topic is required.", ephemeral=True)
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM faq_entries WHERE server_id = $1 AND topic = $2",
                    interaction.guild_id,
                    topic,
                )
            if "DELETE 0" in result:
                await interaction.followup.send(f"No FAQ entry for **{topic}**.", ephemeral=True)
                return
            _invalidate_faq_cache(self.bot.cache, interaction.guild_id, topic)
            await interaction.followup.send(f"FAQ **{topic}** deleted.", ephemeral=True)
        except Exception as e:
            logger.error("faq_delete error: %s", e, exc_info=True)
            await interaction.followup.send("Error deleting FAQ.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(FAQCommands(bot))
