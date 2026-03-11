import asyncio
import logging
import re
from dataclasses import dataclass

from bot.utils.db import TRANSIENT_DB_ERRORS
from bot.utils.regex_validator import RegexValidationError, RegexValidator
from config.constants import Constants

logger = logging.getLogger(__name__)


@dataclass
class PhrasePattern:
    phrase_id: str
    pattern: re.Pattern
    emoji: str
    server_id: int


class PhraseMatcher:
    REGEX_TIMEOUT_SECONDS = 0.5

    def __init__(self, db_pool, cache):
        self.db_pool = db_pool
        self.cache = cache
        self.validator = RegexValidator()
        self._patterns_by_server: dict[int, list[PhrasePattern]] = {}

    async def load_patterns(self, server_id: int):
        cache_key = f"phrase_patterns:{server_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            self._patterns_by_server[server_id] = cached
            return

        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, phrase, emoji FROM phrase_reactions WHERE server_id = $1 AND is_active = true",
                    server_id,
                )
        except TRANSIENT_DB_ERRORS as e:
            logger.warning("Phrase patterns load skipped (DB unavailable): %s", e)
            existing = self._patterns_by_server.get(server_id)
            if existing is not None:
                return
            self._patterns_by_server[server_id] = []
            return

        patterns = []
        for row in rows:
            try:
                patterns.append(
                    PhrasePattern(
                        phrase_id=str(row["id"]),
                        pattern=re.compile(row["phrase"], re.IGNORECASE),
                        emoji=row["emoji"],
                        server_id=server_id,
                    )
                )
            except re.error as e:
                logger.error("Invalid regex %s: %s", row["phrase"], e)

        self._patterns_by_server[server_id] = patterns
        self.cache.set(cache_key, patterns, ttl=Constants.PHRASE_PATTERN_CACHE_TTL)

    async def match_phrases(self, message_content: str, server_id: int) -> list[tuple[str, str]]:
        if server_id not in self._patterns_by_server:
            await self.load_patterns(server_id)

        patterns = self._patterns_by_server.get(server_id, [])
        if not patterns:
            return []

        normalized = self._normalize_message(message_content)
        matches = []
        for p in patterns:
            try:
                if await asyncio.wait_for(
                    self._match_with_timeout(p.pattern, normalized),
                    timeout=self.REGEX_TIMEOUT_SECONDS,
                ):
                    matches.append((p.phrase_id, p.emoji))
            except asyncio.TimeoutError:
                logger.warning("Regex timeout for %s", p.phrase_id)
                await self._disable_pattern(p.phrase_id)
        return matches

    async def _match_with_timeout(self, pattern: re.Pattern, text: str) -> re.Match | None:
        return await asyncio.get_event_loop().run_in_executor(None, pattern.search, text)

    def _normalize_message(self, content: str) -> str:
        return content.lower()

    async def validate_pattern(self, phrase: str) -> None:
        await self.validator.validate(phrase)
        try:
            re.compile(phrase, re.IGNORECASE)
        except re.error as e:
            raise RegexValidationError(f"Invalid regex: {e}")

    async def _disable_pattern(self, phrase_id: str):
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE phrase_reactions SET is_active = false WHERE id = $1", phrase_id
                )
            logger.error("Disabled pattern %s (ReDoS)", phrase_id)
        except TRANSIENT_DB_ERRORS as e:
            logger.warning("Could not disable pattern %s (DB unavailable): %s", phrase_id, e)
        except Exception as e:
            logger.error("Failed to disable %s: %s", phrase_id, e)

    def invalidate_cache(self, server_id: int):
        self.cache.delete(f"phrase_patterns:{server_id}")
        self._patterns_by_server.pop(server_id, None)
