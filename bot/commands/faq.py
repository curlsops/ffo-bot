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


def _paginate_by_char_limit(blocks: list[str], limit: int) -> list[str]:
    pages = []
    current = []
    current_len = 0
    for block in blocks:
        block_len = len(block)
        if current_len + block_len > limit and current:
            pages.append("".join(current))
            current = []
            current_len = 0
        current.append(block)
        current_len += block_len
    if current:
        pages.append("".join(current))
    return pages


class FAQListView(discord.ui.View):
    def __init__(self, pages: list[str], timeout: float = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.page = 0
        self._max_page = max(0, len(pages) - 1)

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id="faq:prev",
            row=0,
        )
        prev_btn.callback = self._prev_callback
        self.add_item(prev_btn)

        self.page_btn = discord.ui.Button(
            label="1/1",
            style=discord.ButtonStyle.success,
            custom_id="faq:page",
            disabled=True,
            row=0,
        )
        self.add_item(self.page_btn)

        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id="faq:next",
            row=0,
        )
        next_btn.callback = self._next_callback
        self.add_item(next_btn)
        self._update_buttons()

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self._max_page + 1}"
        for child in self.children:
            if child.custom_id == "faq:prev":
                child.disabled = self.page <= 0
            elif child.custom_id == "faq:next":
                child.disabled = self.page >= self._max_page

    def _format_page(self) -> discord.Embed:
        embed = discord.Embed(
            title="FAQ",
            description=self.pages[self.page][:4096],
            color=discord.Color.blue(),
        )
        embed.set_footer(
            text=f"Page {self.page + 1}/{len(self.pages)} • Use /faq list topic:<name> for single topic"
        )
        return embed

    async def _prev_callback(self, interaction: discord.Interaction):
        if self.page <= 0:
            return
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._format_page(), view=self)

    async def _next_callback(self, interaction: discord.Interaction):
        if self.page >= self._max_page:
            return
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._format_page(), view=self)


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


@app_commands.guild_only()
class FAQGroup(app_commands.Group):
    """FAQ topics and entries."""

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
                        self.cog.bot.cache.set(cache_key, dict(row), ttl=300)
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
                        self.cog.bot.cache.set(cache_key, rows, ttl=300)
                if not rows:
                    await interaction.followup.send(
                        "No FAQ entries yet. Admins can add them with `/faq add`.",
                        ephemeral=True,
                    )
                    return
                blocks = _build_faq_blocks(rows)
                pages = _paginate_by_char_limit(blocks, FAQ_CHAR_LIMIT_PER_PAGE)
                view = FAQListView(pages)
                await interaction.followup.send(
                    embed=view._format_page(),
                    view=view,
                    ephemeral=True,
                )
        except Exception as e:
            logger.error("faq list error: %s", e, exc_info=True)
            await interaction.followup.send("Error fetching FAQ.", ephemeral=True)

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
        if not interaction.guild_id or not await self.cog._check_admin(interaction, "faq add"):
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
            await interaction.followup.send(f"FAQ **{topic}** added/updated.", ephemeral=True)
        except Exception as e:
            logger.error("faq add error: %s", e, exc_info=True)
            await interaction.followup.send("Error adding FAQ.", ephemeral=True)

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
        if not interaction.guild_id or not await self.cog._check_admin(interaction, "faq edit"):
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
            await interaction.followup.send(f"FAQ **{topic}** updated.", ephemeral=True)
        except Exception as e:
            logger.error("faq edit error: %s", e, exc_info=True)
            await interaction.followup.send("Error editing FAQ.", ephemeral=True)

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
        if not interaction.guild_id or not await self.cog._check_admin(interaction, "faq delete"):
            return

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        if not topic:
            await interaction.followup.send("Topic is required.", ephemeral=True)
            return

        try:
            async with self.cog.bot.db_pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM faq_entries WHERE server_id = $1 AND topic = $2",
                    interaction.guild_id,
                    topic,
                )
            if "DELETE 0" in result:
                await interaction.followup.send(f"No FAQ entry for **{topic}**.", ephemeral=True)
                return
            _invalidate_faq_cache(self.cog.bot.cache, interaction.guild_id, topic)
            await interaction.followup.send(f"FAQ **{topic}** deleted.", ephemeral=True)
        except Exception as e:
            logger.error("faq delete error: %s", e, exc_info=True)
            await interaction.followup.send("Error deleting FAQ.", ephemeral=True)


class FAQCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.faq_group = FAQGroup(self)

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

    async def cog_load(self):
        self.bot.tree.add_command(self.faq_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.faq_group.name)


async def setup(bot):
    await bot.add_cog(FAQCommands(bot))
