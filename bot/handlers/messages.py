import asyncio
import logging
from typing import Awaitable, cast

import asyncpg
import discord
from discord.ext import commands
from opentelemetry import trace

from bot.commands.whitelist import WHITELIST_APPROVE_EMOJI, WHITELIST_REJECT_EMOJI
from bot.processors.unit_converter import detect_and_convert
from bot.services.mojang import get_profile
from bot.utils.pagination import truncate_for_discord
from bot.utils.user_preferences import OPT_OUT_CACHE_KEY
from bot.utils.whitelist_channel import get_whitelist_channel_id
from config.constants import Constants

logger = logging.getLogger(__name__)


def _message_tracer():
    return trace.get_tracer(__name__)


MOJANG_CACHE_TTL = 300
MOJANG_CACHE_KEY = "mojang:profile:{username}"
_MOJANG_NOT_FOUND = object()
MESSAGE_HANDLER_MAX_CONCURRENCY = 3
MESSAGE_HANDLER_DB_HEAVY_CONCURRENCY = 1


class MessageHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or self.bot.is_shutting_down():
            return

        task = asyncio.current_task()
        if task and not task.done():
            self.bot._message_handler_tasks.add(task)
        try:
            if getattr(self.bot.settings, "otel_trace_discord_messages", False):
                with _message_tracer().start_as_current_span("discord.message") as span:
                    span.set_attribute("discord.guild_id", str(message.guild.id))
                    span.set_attribute("discord.channel_id", str(message.channel.id))
                    await self._handle_message(message)
            else:
                await self._handle_message(message)
        finally:
            if task:
                self.bot._message_handler_tasks.discard(task)

    async def _handle_message(self, message: discord.Message):
        if self.bot.metrics:
            self.bot.metrics.messages_processed.labels(server_id=str(message.guild.id)).inc()

        if await self._check_user_opt_out(message.guild.id, message.author.id):
            return

        operations: list[tuple[bool, Awaitable[None]]] = []
        if message.content and self.bot.phrase_matcher:
            operations.append((True, self._process_phrase_matching(message)))

        vt = getattr(self.bot, "voice_transcriber", None)
        if message.attachments and vt and vt.enabled:
            operations.append((False, self._transcribe_voice_messages(message)))

        if message.content and getattr(self.bot.settings, "feature_conversion", False):
            operations.append((False, self._convert_units(message)))

        await self._run_bounded_operations(operations)

        if getattr(self.bot.settings, "feature_minecraft_whitelist", False):
            await self._process_whitelist_channel(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content or not after.content or after.author.bot:
            return
        if not after.guild or self.bot.is_shutting_down():
            return
        if not self.bot.phrase_matcher:
            return
        if await self._check_user_opt_out(after.guild.id, after.author.id):
            return

        if self.bot.metrics:
            self.bot.metrics.messages_processed.labels(server_id=str(after.guild.id)).inc()

        if getattr(self.bot.settings, "otel_trace_discord_messages", False):
            with _message_tracer().start_as_current_span("discord.message_edit") as span:
                span.set_attribute("discord.guild_id", str(after.guild.id))
                span.set_attribute("discord.channel_id", str(after.channel.id))
                await self._process_phrase_matching_edit(after)
        else:
            await self._process_phrase_matching_edit(after)

    async def _process_phrase_matching_edit(self, message: discord.Message):
        try:
            matches = await self.bot.phrase_matcher.match_phrases(message.content, message.guild.id)
            should_have = {emoji for _, emoji in matches}

            try:
                msg = await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return

            current_ours = {str(r.emoji) for r in msg.reactions if r.me}
            to_add = should_have - current_ours
            to_remove = current_ours - should_have
            phrase_ids_by_emoji = self._phrase_ids_by_emoji(matches)

            for emoji in to_remove:
                await self._try_remove_reaction(msg, emoji)

            logged: list[tuple[int, int, int, int, str, str]] = []
            for emoji in to_add:
                if not await self._try_add_reaction(msg, emoji):
                    continue
                for phrase_id in phrase_ids_by_emoji.get(emoji, []):
                    self._record_phrase_match(
                        source_message=message,
                        phrase_id=phrase_id,
                        emoji=emoji,
                        logged_rows=logged,
                    )
            if logged:
                await self._log_phrase_matches_batch(logged)
        except Exception as e:
            logger.error("Phrase matching edit error: %s", e, exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="phrase_matching").inc()

    async def _process_whitelist_channel(self, message: discord.Message):
        if not message.guild or not message.content:
            return
        channel_id = await get_whitelist_channel_id(
            self.bot.db_pool, message.guild.id, cache=self.bot.cache
        )
        if channel_id != message.channel.id:
            return

        content = message.content.strip()
        if not content or " " in content:
            return

        if not (3 <= len(content) <= 16) or not content.replace("_", "").isalnum():
            return

        username = content
        profile = await self._get_mojang_profile_cached(username)
        if profile:
            uuid_val, _ = profile
            try:
                await message.add_reaction(WHITELIST_APPROVE_EMOJI)
                await message.add_reaction(WHITELIST_REJECT_EMOJI)
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO whitelist_pending (server_id, message_id, channel_id, username, author_id, minecraft_uuid)
                        VALUES ($1, $2, $3, $4, $5, $6::uuid)
                        ON CONFLICT (server_id, message_id) DO NOTHING
                        """,
                        message.guild.id,
                        message.id,
                        message.channel.id,
                        username,
                        message.author.id,
                        uuid_val,
                    )
            except discord.HTTPException as e:
                logger.warning("Failed to add whitelist reactions: %s", e)
            except asyncpg.PostgresError as e:
                logger.error("Whitelist pending insert error: %s", e, exc_info=True)
        else:
            await message.reply(
                f"{message.author.mention} Your Minecraft username does not exist. Please try again."
            )

    async def _process_phrase_matching(self, message: discord.Message):
        try:
            matches = await self.bot.phrase_matcher.match_phrases(message.content, message.guild.id)
            logged: list[tuple[int, int, int, int, str, str]] = []
            for phrase_id, emoji in matches:
                if not await self._try_add_reaction(message, emoji):
                    continue
                self._record_phrase_match(
                    source_message=message,
                    phrase_id=phrase_id,
                    emoji=emoji,
                    logged_rows=logged,
                )
            if logged:
                await self._log_phrase_matches_batch(logged)
        except Exception as e:
            logger.error("Phrase matching error: %s", e, exc_info=True)
            if self.bot.metrics:
                self.bot.metrics.errors_total.labels(error_type="phrase_matching").inc()

    async def _run_bounded_operations(self, operations: list[tuple[bool, Awaitable[None]]]):
        if not operations:
            return

        run_semaphore = asyncio.Semaphore(MESSAGE_HANDLER_MAX_CONCURRENCY)
        db_heavy_semaphore = asyncio.Semaphore(MESSAGE_HANDLER_DB_HEAVY_CONCURRENCY)

        async def run_one(is_db_heavy: bool, operation):
            async with run_semaphore:
                if is_db_heavy:
                    async with db_heavy_semaphore:
                        _ = await operation
                else:
                    _ = await operation

        await asyncio.gather(
            *(run_one(is_db_heavy, operation) for is_db_heavy, operation in operations)
        )

    @staticmethod
    def _phrase_ids_by_emoji(matches: list[tuple[str, str]]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for phrase_id, emoji in matches:
            grouped.setdefault(emoji, []).append(phrase_id)
        return grouped

    async def _try_add_reaction(self, message: discord.Message, emoji: str) -> bool:
        try:
            await message.add_reaction(emoji)
            return True
        except discord.HTTPException as e:
            logger.warning("Failed to add reaction %s: %s", emoji, e)
            return False

    async def _try_remove_reaction(self, message: discord.Message, emoji: str):
        try:
            await message.remove_reaction(emoji, self.bot.user)
        except discord.HTTPException as e:
            logger.warning("Failed to remove reaction %s: %s", emoji, e)

    def _record_phrase_match(
        self,
        source_message: discord.Message,
        phrase_id: str,
        emoji: str,
        logged_rows: list[tuple[int, int, int, int, str, str]],
    ):
        if self.bot.metrics:
            self.bot.metrics.phrase_matches.labels(
                server_id=str(source_message.guild.id), phrase_id=phrase_id
            ).inc()
        logged_rows.append(
            (
                source_message.guild.id,
                source_message.id,
                source_message.channel.id,
                source_message.author.id,
                phrase_id,
                emoji,
            )
        )

    async def _get_mojang_profile_cached(self, username: str):
        key = MOJANG_CACHE_KEY.format(username=username.lower())
        if self.bot.cache:
            cached = self.bot.cache.get(key)
            if cached is not None:
                return None if cached is _MOJANG_NOT_FOUND else cached
        profile = await get_profile(username)
        if self.bot.cache:
            self.bot.cache.set(
                key, _MOJANG_NOT_FOUND if profile is None else profile, ttl=MOJANG_CACHE_TTL
            )
        return profile

    async def _log_phrase_matches_batch(
        self,
        rows: list[tuple[int, int, int, int, str, str]],
    ):
        if not rows:
            return
        try:
            seen_msg: dict[int, tuple[int, int, int, int, str, str]] = {}
            for server_id, message_id, channel_id, user_id, phrase_id, emoji in rows:
                if message_id not in seen_msg:
                    seen_msg[message_id] = (
                        server_id,
                        message_id,
                        channel_id,
                        user_id,
                        phrase_id,
                        emoji,
                    )
            phrase_ids = [r[4] for r in rows]
            async with self.bot.db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO message_metadata (server_id, message_id, channel_id, user_id, phrase_matched, reaction_added)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (message_id) DO NOTHING
                    """,
                    list(seen_msg.values()),
                )
                await conn.execute(
                    """
                    UPDATE phrase_reactions pr
                    SET match_count = match_count + sub.cnt, last_matched_at = NOW()
                    FROM (
                        SELECT id, COUNT(*)::int AS cnt
                        FROM unnest($1::text[]) AS id
                        GROUP BY id
                    ) sub
                    WHERE pr.id = sub.id
                    """,
                    phrase_ids,
                )
        except asyncpg.PostgresError as e:
            logger.error("Failed to log phrase matches: %s", e)

    async def _convert_units(self, message: discord.Message):
        try:
            converted = detect_and_convert(message.content)
            if converted:
                embed = discord.Embed(
                    description=converted,
                    color=discord.Color.blue(),
                )
                embed.set_footer(text="Converted from imperial to SI")
                await message.reply(embed=embed, mention_author=False)
        except Exception as e:
            logger.warning("Unit conversion error: %s", e)

    async def _transcribe_voice_messages(self, message: discord.Message):
        vt = getattr(self.bot, "voice_transcriber", None)
        if not vt:
            return
        atts = [
            att
            for att in message.attachments
            if vt.is_voice_attachment(att.filename, att.content_type)
        ]
        if not atts:
            return
        results = await asyncio.gather(
            *[vt.transcribe(att.url, att.filename) for att in atts],
            return_exceptions=True,
        )
        for att, result in zip(atts, results):
            if isinstance(result, Exception):
                logger.error("Voice transcription error: %s", result, exc_info=True)
            elif result:
                embed = discord.Embed(
                    description=truncate_for_discord(cast(str, result)),
                    color=discord.Color.blue(),
                )
                embed.set_author(
                    name=f"Voice message from {message.author.display_name}",
                    icon_url=message.author.display_avatar.url,
                )
                embed.set_footer(text="Transcribed automatically")
                await message.reply(embed=embed)

    async def _check_user_opt_out(self, server_id: int, user_id: int) -> bool:
        cache_key = OPT_OUT_CACHE_KEY.format(server_id=server_id, user_id=user_id)
        if self.bot.cache:
            cached = self.bot.cache.get(cache_key)
            if cached is not None:
                return bool(cached)
        try:
            async with self.bot.db_pool.acquire() as conn:
                val = await conn.fetchval(
                    "SELECT message_tracking_opt_out FROM user_preferences WHERE server_id = $1 AND user_id = $2",
                    server_id,
                    user_id,
                )
            result = bool(val)
            if self.bot.cache:
                self.bot.cache.set(cache_key, result, ttl=Constants.CACHE_TTL)
            return result
        except asyncpg.PostgresError as e:
            logger.debug(
                "_check_user_opt_out failed server_id=%s user_id=%s: %s", server_id, user_id, e
            )
            return False


async def setup(bot):
    await bot.add_cog(MessageHandler(bot))
