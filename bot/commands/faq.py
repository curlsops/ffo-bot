import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.auth.command_helpers import execute_command, require_admin, send_error
from bot.services.faq_service import CACHE_FAQ_TOPICS, FaqService
from bot.utils.autocomplete import cached_autocomplete
from bot.utils.log_context import log_command_start
from bot.utils.pagination import EmbedPaginatedView, paginate_by_char_limit
from config.constants import Constants

logger = logging.getLogger(__name__)

MAX_ANSWER_LEN = 1024
MAX_QUESTION_LEN = 200
MAX_TOPIC_LEN = 100
MAX_TOPICS = 25
FAQ_CHAR_LIMIT_PER_PAGE = 1800


def _build_faq_blocks(rows: list) -> list[str]:
    blocks = []
    for r in rows:
        block = f"**{r['topic']}**\n**Q:** {r['question']}\n**A:** {r['answer']}\n\n"
        blocks.append(block)
    return blocks


FAQ_LIST_FOOTER = "Page {page}/{total} • Use /faq list topic:<name> for single topic"


async def _fetch_faq_topics(pool, guild_id: int):
    return await FaqService(pool).list_topics(guild_id)


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


async def _faq_add_check(
    self: "FAQGroup", interaction: discord.Interaction, topic: str, question: str, answer: str
) -> bool:
    return await require_admin(interaction, "faq add", self.cog.bot)


async def _faq_edit_check(
    self: "FAQGroup",
    interaction: discord.Interaction,
    topic: str,
    question: str | None = None,
    answer: str | None = None,
) -> bool:
    return await require_admin(interaction, "faq edit", self.cog.bot)


async def _faq_submissions_check(self: "FAQGroup", interaction: discord.Interaction) -> bool:
    return await require_admin(interaction, "faq submissions", self.cog.bot)


async def _faq_delete_check(self: "FAQGroup", interaction: discord.Interaction, topic: str) -> bool:
    return await require_admin(interaction, "faq delete", self.cog.bot)


@app_commands.guild_only()
class FAQGroup(app_commands.Group):
    def __init__(self, cog: "FAQCommands"):
        super().__init__(name="faq", description="FAQ topics and entries")
        self.cog = cog

    @app_commands.command(name="list", description="List FAQ topics or show a specific topic")
    @app_commands.describe(topic="Topic to look up (leave empty to list all)")
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    @execute_command(
        error_message="Error fetching FAQ.",
        logger=logger,
        log_prefix="faq list error",
    )
    async def list_cmd(
        self,
        interaction: discord.Interaction,
        topic: str | None = None,
    ):
        log_command_start(logger, "faq", "faq list", interaction)
        if not interaction.guild_id:
            return

        topic_key = topic.strip().lower() if topic else None
        if topic_key:
            row = await self.cog.service.fetch_entry(
                interaction.guild_id, topic_key, cache=self.cog.bot.cache
            )
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
            rows = await self.cog.service.fetch_all_entries(
                interaction.guild_id, cache=self.cog.bot.cache
            )
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

    @app_commands.command(
        name="submit",
        description="Submit a question you'd like answered in the FAQ",
    )
    @app_commands.describe(question="Your question (max 200 chars)")
    @execute_command(
        error_message="Error submitting question.",
        logger=logger,
        log_prefix="faq submit error",
    )
    async def submit_cmd(
        self,
        interaction: discord.Interaction,
        question: str,
    ):
        log_command_start(logger, "faq", "faq submit", interaction)
        if not interaction.guild_id:
            return
        if not self.cog.bot.settings.feature_faq_submissions:
            await send_error(interaction, "FAQ submissions are disabled.")
            return
        q = question.strip()[:MAX_QUESTION_LEN]
        if not q:
            await send_error(interaction, "Question cannot be empty.")
            return

        submission_id = await self.cog.service.submit_question(
            interaction.guild_id, q, interaction.user.id
        )
        if submission_id and self.cog.bot.notifier:
            await self.cog.bot.notifier.notify_faq_submission(
                interaction.guild_id,
                q,
                interaction.user.id,
                submission_id,
            )
        await interaction.followup.send(
            "Question submitted! Admins will review it and may add it to the FAQ.",
            ephemeral=True,
        )

    @app_commands.command(name="add", description="Add a FAQ entry (Admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        topic="Topic/slug (e.g. whitelist, rules)",
        question="The question or topic title",
        answer="The answer (max 1024 chars)",
    )
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    @execute_command(
        permission_check=_faq_add_check,
        error_message="Error adding FAQ.",
        logger=logger,
        log_prefix="faq add error",
    )
    async def add_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
        question: str,
        answer: str,
    ):
        log_command_start(logger, "faq", "faq add", interaction)

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        question = question.strip()[:MAX_QUESTION_LEN]
        answer = answer.strip()[:MAX_ANSWER_LEN]

        if not topic or not question or not answer:
            await interaction.followup.send(
                "Topic, question, and answer are required.",
                ephemeral=True,
            )
            return

        count = await self.cog.service.count_entries(interaction.guild_id)
        if count and count >= MAX_TOPICS:
            await interaction.followup.send(
                f"Maximum {MAX_TOPICS} FAQ topics per server.",
                ephemeral=True,
            )
            return

        await self.cog.service.upsert_entry(
            interaction.guild_id, topic, question, answer, cache=self.cog.bot.cache
        )
        if self.cog.bot.notifier:
            await self.cog.bot.notifier.notify_faq_changed(
                interaction.guild_id, "Added/Updated", topic, interaction.user.id
            )
        await interaction.followup.send(f"FAQ **{topic}** added/updated.", ephemeral=True)

    @app_commands.command(name="edit", description="Edit a FAQ entry (Admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        topic="Topic to edit",
        question="New question (leave empty to keep)",
        answer="New answer (leave empty to keep)",
    )
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    @execute_command(
        permission_check=_faq_edit_check,
        error_message="Error editing FAQ.",
        logger=logger,
        log_prefix="faq edit error",
    )
    async def edit_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
        question: str | None = None,
        answer: str | None = None,
    ):
        log_command_start(logger, "faq", "faq edit", interaction)

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

        new_q = question.strip()[:MAX_QUESTION_LEN] if question else None
        new_a = answer.strip()[:MAX_ANSWER_LEN] if answer else None

        row = await self.cog.service.edit_entry(
            interaction.guild_id, topic, new_q, new_a, cache=self.cog.bot.cache
        )
        if not row:
            await interaction.followup.send(f"No FAQ entry for **{topic}**.", ephemeral=True)
            return
        if self.cog.bot.notifier:
            await self.cog.bot.notifier.notify_faq_changed(
                interaction.guild_id, "Edited", topic, interaction.user.id
            )
        await interaction.followup.send(f"FAQ **{topic}** updated.", ephemeral=True)

    @app_commands.command(
        name="submissions",
        description="List pending FAQ question submissions (Admin)",
    )
    @app_commands.default_permissions(administrator=True)
    @execute_command(
        permission_check=_faq_submissions_check,
        error_message="Error fetching submissions.",
        logger=logger,
        log_prefix="faq submissions error",
    )
    async def submissions_cmd(self, interaction: discord.Interaction):
        log_command_start(logger, "faq", "faq submissions", interaction)
        rows = await self.cog.service.list_submissions(interaction.guild_id)
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

    @app_commands.command(name="delete", description="Delete a FAQ entry (Admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(topic="Topic to delete")
    @app_commands.autocomplete(topic=_faq_topic_autocomplete)
    @execute_command(
        permission_check=_faq_delete_check,
        error_message="Error deleting FAQ.",
        logger=logger,
        log_prefix="faq delete error",
    )
    async def delete_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
    ):
        log_command_start(logger, "faq", "faq delete", interaction)

        topic = topic.strip().lower()[:MAX_TOPIC_LEN]
        if not topic:
            await send_error(interaction, "Topic is required.")
            return

        deleted = await self.cog.service.delete_entry(
            interaction.guild_id, topic, cache=self.cog.bot.cache
        )
        if not deleted:
            await send_error(interaction, f"No FAQ entry for **{topic}**.")
            return
        if self.cog.bot.notifier:
            await self.cog.bot.notifier.notify_faq_changed(
                interaction.guild_id, "Deleted", topic, interaction.user.id
            )
        await interaction.followup.send(f"FAQ **{topic}** deleted.", ephemeral=True)


class FAQCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = FaqService(bot.db_pool)
        self.faq_group = FAQGroup(self)

    async def cog_load(self):
        self.bot.tree.add_command(self.faq_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.faq_group.name)


async def setup(bot):
    await bot.add_cog(FAQCommands(bot))
