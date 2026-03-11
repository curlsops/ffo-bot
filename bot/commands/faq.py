import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import require_admin, send_error
from bot.utils.autocomplete import cached_autocomplete
from bot.utils.pagination import EmbedPaginatedView, paginate_by_char_limit
from config.constants import Constants

logger = logging.getLogger(__name__)

MAX_ANSWER_LEN = 1024
MAX_QUESTION_LEN = 200
MAX_TOPIC_LEN = 100
MAX_TOPICS = 25
FAQ_CHAR_LIMIT_PER_PAGE = 1800

CACHE_FAQ_TOPICS = "faq_topics:{server_id}"
CACHE_FAQ_ENTRY = "faq_entry:{server_id}:{topic}"
CACHE_FAQ_ALL = "faq_all:{server_id}"


def _invalidate_faq_cache(cache, server_id: int, topic: str | None = None) -> None:
    if cache:
        cache.delete(CACHE_FAQ_TOPICS.format(server_id=server_id))
        cache.delete(CACHE_FAQ_ALL.format(server_id=server_id))
        if topic:
            cache.delete(CACHE_FAQ_ENTRY.format(server_id=server_id, topic=topic))


def _build_faq_blocks(rows: list) -> list[str]:
    blocks = []
    for r in rows:
        block = f"**{r['topic']}**\n**Q:** {r['question']}\n**A:** {r['answer']}\n\n"
        blocks.append(block)
    return blocks


FAQ_LIST_FOOTER = "Page {page}/{total} • Use /faq list topic:<name> for single topic"


async def _fetch_faq_topics(pool, guild_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT topic FROM faq_entries
            WHERE server_id = $1
            ORDER BY sort_order, topic
            """,
            guild_id,
        )


def _faq_topics_to_choices(rows: list[dict], current: str) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=r["topic"], value=r["topic"])
        for r in rows
        if not current or current.lower() in r["topic"].lower()
    ]


async def _faq_topic_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return await cached_autocomplete(
        interaction,
        current,
        CACHE_FAQ_TOPICS,
        _fetch_faq_topics,
        _faq_topics_to_choices,
        ttl=Constants.CACHE_TTL,
        log_prefix="FAQ topic",
    )


@app_commands.guild_only()
class FAQGroup(app_commands.Group):
    def __init__(self, cog: "FAQCommands"):
        super().__init__(name="faq", description="FAQ topics and entries")
        self.cog = cog

    @app_commands.command(name="list", description="List FAQ topics or show a specific topic")
    @app_commands.describe(topic="Topic to look up (leave empty to list all)")
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def list_cmd(
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
                row = self.cog.bot.cache.get(cache_key) if self.cog.bot.cache else None
                if row is None:
                    async with self.cog.bot.db_pool.acquire() as conn:
                        row = await conn.fetchrow(
                            """
                            SELECT question, answer FROM faq_entries
                            WHERE server_id = $1 AND topic = $2
                            """,
                            interaction.guild_id,
                            topic_key,
                        )
                    if row and self.cog.bot.cache:
                        self.cog.bot.cache.set(cache_key, dict(row), ttl=Constants.CACHE_TTL)
                if not row:
                    await interaction.followup.send(
                        f"No FAQ entry for **{topic}**. Use `/faq list` with no topic to list.",
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
                cache_key = CACHE_FAQ_ALL.format(server_id=interaction.guild_id)
                rows = self.cog.bot.cache.get(cache_key) if self.cog.bot.cache else None
                if rows is None:
                    async with self.cog.bot.db_pool.acquire() as conn:
                        rows = await conn.fetch(
                            """
                            SELECT topic, question, answer FROM faq_entries
                            WHERE server_id = $1
                            ORDER BY sort_order, topic
                            """,
                            interaction.guild_id,
                        )
                    rows = [dict(r) for r in rows]
                    if self.cog.bot.cache:
                        self.cog.bot.cache.set(cache_key, rows, ttl=Constants.CACHE_TTL)
                if not rows:
                    await interaction.followup.send(
                        "No FAQ entries yet. Admins can add them with `/faq add`.",
                        ephemeral=True,
                    )
                    return
                blocks = _build_faq_blocks(rows)
                pages = paginate_by_char_limit(blocks, FAQ_CHAR_LIMIT_PER_PAGE)
                view = EmbedPaginatedView(pages, title="FAQ", footer_template=FAQ_LIST_FOOTER)
                await interaction.followup.send(
                    embed=view._format_page(),
                    view=view,
                    ephemeral=True,
                )
        except Exception as e:
            logger.error("faq list error: %s", e, exc_info=True)
            await send_error(interaction, "Error fetching FAQ.")

    @app_commands.command(
        name="submit",
        description="Submit a question you'd like answered in the FAQ",
    )
    @app_commands.describe(question="Your question (max 200 chars)")
    async def submit_cmd(
        self,
        interaction: discord.Interaction,
        question: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return
        if not self.cog.bot.settings.feature_faq_submissions:
            await send_error(interaction, "FAQ submissions are disabled.")
            return
        q = question.strip()[:MAX_QUESTION_LEN]
        if not q:
            await send_error(interaction, "Question cannot be empty.")
            return
        try:
            row = None
            async with self.cog.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO faq_submissions (server_id, question, submitter_id)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    interaction.guild_id,
                    q,
                    interaction.user.id,
                )
            if row and self.cog.bot.notifier:
                await self.cog.bot.notifier.notify_faq_submission(
                    interaction.guild_id,
                    q,
                    interaction.user.id,
                    str(row["id"]),
                )
            await interaction.followup.send(
                "Question submitted! Admins will review it and may add it to the FAQ.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("faq submit error: %s", e, exc_info=True)
            await send_error(interaction, "Error submitting question.")

    @app_commands.command(name="add", description="Add a FAQ entry (Admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        topic="Topic/slug (e.g. whitelist, rules)",
        question="The question or topic title",
        answer="The answer (max 1024 chars)",
    )
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def add_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
        question: str,
        answer: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await require_admin(interaction, "faq add", self.cog.bot):
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
            async with self.cog.bot.db_pool.acquire() as conn:
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
            _invalidate_faq_cache(self.cog.bot.cache, interaction.guild_id, topic)
            if self.cog.bot.notifier:
                await self.cog.bot.notifier.notify_faq_changed(
                    interaction.guild_id, "Added/Updated", topic, interaction.user.id
                )
            await interaction.followup.send(f"FAQ **{topic}** added/updated.", ephemeral=True)
        except Exception as e:
            logger.error("faq add error: %s", e, exc_info=True)
            await send_error(interaction, "Error adding FAQ.")

    @app_commands.command(name="edit", description="Edit a FAQ entry (Admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        topic="Topic to edit",
        question="New question (leave empty to keep)",
        answer="New answer (leave empty to keep)",
    )
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def edit_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
        question: str | None = None,
        answer: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await require_admin(interaction, "faq edit", self.cog.bot):
            return

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        if not topic:
            await send_error(interaction, "Topic is required.")
            return

        if not question and not answer:
            await interaction.followup.send(
                "Provide at least question or answer to update.",
                ephemeral=True,
            )
            return

        try:
            async with self.cog.bot.db_pool.acquire() as conn:
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
            _invalidate_faq_cache(self.cog.bot.cache, interaction.guild_id, topic)
            if self.cog.bot.notifier:
                await self.cog.bot.notifier.notify_faq_changed(
                    interaction.guild_id, "Edited", topic, interaction.user.id
                )
            await interaction.followup.send(f"FAQ **{topic}** updated.", ephemeral=True)
        except Exception as e:
            logger.error("faq edit error: %s", e, exc_info=True)
            await send_error(interaction, "Error editing FAQ.")

    @app_commands.command(
        name="submissions",
        description="List pending FAQ question submissions (Admin)",
    )
    @app_commands.default_permissions(administrator=True)
    async def submissions_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await require_admin(interaction, "faq submissions", self.cog.bot):
            return
        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, question, submitter_id, created_at
                    FROM faq_submissions
                    WHERE server_id = $1
                    ORDER BY created_at DESC
                    LIMIT 25
                    """,
                    interaction.guild_id,
                )
            if not rows:
                await interaction.followup.send(
                    "No pending FAQ submissions.",
                    ephemeral=True,
                )
                return
            lines = []
            for r in rows:
                short = (r["question"][:60] + "…") if len(r["question"]) > 60 else r["question"]
                lines.append(f"`{str(r['id'])[:8]}` <@{r['submitter_id']}>: {short}")
            await interaction.followup.send(
                "**Pending FAQ submissions:**\n" + "\n".join(lines),
                ephemeral=True,
            )
        except Exception as e:
            logger.error("faq submissions error: %s", e, exc_info=True)
            await interaction.followup.send(
                "Error fetching submissions.",
                ephemeral=True,
            )

    @app_commands.command(name="delete", description="Delete a FAQ entry (Admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(topic="Topic to delete")
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    async def delete_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await require_admin(interaction, "faq delete", self.cog.bot):
            return

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        if not topic:
            await send_error(interaction, "Topic is required.")
            return

        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM faq_entries WHERE server_id = $1 AND topic = $2",
                    interaction.guild_id,
                    topic,
                )
            if "DELETE 0" in result:
                await send_error(interaction, f"No FAQ entry for **{topic}**.")
                return
            _invalidate_faq_cache(self.cog.bot.cache, interaction.guild_id, topic)
            if self.cog.bot.notifier:
                await self.cog.bot.notifier.notify_faq_changed(
                    interaction.guild_id, "Deleted", topic, interaction.user.id
                )
            await interaction.followup.send(f"FAQ **{topic}** deleted.", ephemeral=True)
        except Exception as e:
            logger.error("faq delete error: %s", e, exc_info=True)
            await send_error(interaction, "Error deleting FAQ.")


class FAQCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.faq_group = FAQGroup(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.faq_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.faq_group.name)


async def setup(bot):
    await bot.add_cog(FAQCommands(bot))
