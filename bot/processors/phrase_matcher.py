"""Phrase matching with ReDoS protection."""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from bot.utils.regex_validator import RegexValidationError, RegexValidator

logger = logging.getLogger(__name__)


@dataclass
class PhrasePattern:
    """Compiled phrase pattern with metadata."""

    phrase_id: str
    pattern: re.Pattern
    emoji: str
    server_id: int


class PhraseMatcher:
    """Message phrase detection with ReDoS protection."""

    # Regex timeout to prevent ReDoS
    REGEX_TIMEOUT_SECONDS = 0.5

    def __init__(self, db_pool, cache):
        """
        Initialize phrase matcher.

        Args:
            db_pool: Database connection pool
            cache: In-memory cache
        """
        self.db_pool = db_pool
        self.cache = cache
        self.validator = RegexValidator()
        self._patterns_by_server: Dict[int, List[PhrasePattern]] = {}

    async def load_patterns(self, server_id: int):
        """
        Load and compile regex patterns for server.

        Args:
            server_id: Discord server ID
        """
        cache_key = f"phrase_patterns:{server_id}"
        cached = self.cache.get(cache_key)

        if cached is not None:
            self._patterns_by_server[server_id] = cached
            return

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, phrase, emoji
                FROM phrase_reactions
                WHERE server_id = $1 AND is_active = true
                """,
                server_id,
            )

        patterns = []
        for row in rows:
            try:
                # Compile case-insensitive pattern
                pattern = re.compile(row["phrase"], re.IGNORECASE)
                patterns.append(
                    PhrasePattern(
                        phrase_id=str(row["id"]),
                        pattern=pattern,
                        emoji=row["emoji"],
                        server_id=server_id,
                    )
                )
            except re.error as e:
                logger.error(f"Invalid regex pattern {row['phrase']}: {e}")

        self._patterns_by_server[server_id] = patterns

        # Cache patterns for 5 minutes
        self.cache.set(cache_key, patterns, ttl=300)

        logger.info(f"Loaded {len(patterns)} patterns for server {server_id}")

    async def match_phrases(self, message_content: str, server_id: int) -> List[Tuple[str, str]]:
        """
        Match message against all patterns for server.

        Args:
            message_content: Message text to match
            server_id: Discord server ID

        Returns:
            List of (phrase_id, emoji) tuples
        """
        if server_id not in self._patterns_by_server:
            await self.load_patterns(server_id)

        patterns = self._patterns_by_server[server_id]

        if not patterns:
            return []

        # Normalize message content
        normalized_content = self._normalize_message(message_content)

        matches = []
        for phrase_pattern in patterns:
            try:
                # Run regex with timeout protection
                match = await asyncio.wait_for(
                    self._match_with_timeout(phrase_pattern.pattern, normalized_content),
                    timeout=self.REGEX_TIMEOUT_SECONDS,
                )

                if match:
                    matches.append((phrase_pattern.phrase_id, phrase_pattern.emoji))
                    logger.debug(
                        f"Phrase match: {phrase_pattern.phrase_id} -> {phrase_pattern.emoji}"
                    )

            except asyncio.TimeoutError:
                logger.warning(
                    f"Regex timeout for pattern {phrase_pattern.phrase_id} "
                    f"in server {server_id}"
                )
                # Disable problematic pattern
                await self._disable_pattern(phrase_pattern.phrase_id)

        return matches

    async def _match_with_timeout(self, pattern: re.Pattern, text: str) -> Optional[re.Match]:
        """
        Run regex match in executor to enable timeout.

        Args:
            pattern: Compiled regex pattern
            text: Text to match against

        Returns:
            Match object or None
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, pattern.search, text)

    def _normalize_message(self, content: str) -> str:
        """
        Normalize message for matching.

        Args:
            content: Raw message content

        Returns:
            Normalized content
        """
        # Keep letters, numbers, and spaces only for more reliable matching
        return re.sub(r"[^a-zA-Z0-9\s]", "", content).lower()

    async def validate_pattern(self, phrase: str) -> None:
        """
        Validate regex pattern before storing.

        Args:
            phrase: Regex pattern to validate

        Raises:
            RegexValidationError: If pattern is invalid or dangerous
        """
        # Check for ReDoS vulnerabilities
        await self.validator.validate(phrase)

        # Additional length check
        if len(phrase) > 500:
            raise RegexValidationError("Pattern exceeds maximum length of 500 characters")

        # Test compilation
        try:
            re.compile(phrase, re.IGNORECASE)
        except re.error as e:
            raise RegexValidationError(f"Invalid regex syntax: {e}")

    async def _disable_pattern(self, phrase_id: str):
        """
        Disable problematic pattern in database.

        Args:
            phrase_id: Phrase reaction ID to disable
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE phrase_reactions
                    SET is_active = false
                    WHERE id = $1
                    """,
                    phrase_id,
                )

            logger.error(f"Disabled phrase pattern {phrase_id} due to ReDoS risk")
        except Exception as e:
            logger.error(f"Failed to disable pattern {phrase_id}: {e}")

    def invalidate_cache(self, server_id: int):
        """
        Clear cached patterns for server after configuration change.

        Args:
            server_id: Discord server ID
        """
        cache_key = f"phrase_patterns:{server_id}"
        self.cache.delete(cache_key)

        if server_id in self._patterns_by_server:
            del self._patterns_by_server[server_id]

        logger.debug(f"Invalidated phrase cache for server {server_id}")
