import asyncio
import re
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.processors.phrase_matcher import PhraseMatcher, PhrasePattern
from bot.utils.regex_validator import RegexValidationError


class TestPhrasePattern:
    def test_phrase_pattern_creation(self):
        pattern = re.compile(r"hello", re.IGNORECASE)
        phrase_pattern = PhrasePattern(phrase_id="123", pattern=pattern, emoji="👋", server_id=456)
        assert phrase_pattern.phrase_id == "123"
        assert phrase_pattern.pattern == pattern
        assert phrase_pattern.emoji == "👋"
        assert phrase_pattern.server_id == 456


class TestPhraseMatcherInit:
    def test_matcher_initialization(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher.db_pool == mock_db_pool
        assert matcher.cache == mock_cache
        assert matcher.validator is not None
        assert matcher._patterns_by_server == {}


class TestPhraseMatcherNormalization:
    def test_normalize_message_basic(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher._normalize_message("Hello World!") == "hello world!"

    def test_normalize_message_preserves_punctuation(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher._normalize_message("Hello, World! How are you?") == "hello, world! how are you?"

    def test_normalize_message_strips_discord_noise(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher._normalize_message("Hello @user #channel $money") == "hello user channel money"

    def test_normalize_message_preserves_numbers(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher._normalize_message("Test 123 Message") == "test 123 message"

    def test_normalize_message_lowercase(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher._normalize_message("UPPERCASE MESSAGE") == "uppercase message"

    def test_normalize_message_preserves_emoticons(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher._normalize_message(":3") == ":3"
        assert matcher._normalize_message("UwU :3 OwO") == "uwu :3 owo"


class TestPhraseMatcherCacheInvalidation:
    def test_invalidate_cache(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [MagicMock()]
        matcher.invalidate_cache(123)
        assert 123 not in matcher._patterns_by_server

    def test_invalidate_cache_nonexistent_server(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher.invalidate_cache(999)


class TestPhraseMatcherAsync:
    @pytest.mark.asyncio
    async def test_load_patterns_from_cache(self, mock_db_pool, mock_cache):
        cached_patterns = [
            PhrasePattern(phrase_id="1", pattern=re.compile(r"hello"), emoji="👋", server_id=123)
        ]
        mock_cache.set("phrase_patterns:123", cached_patterns)
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        await matcher.load_patterns(123)
        assert matcher._patterns_by_server[123] == cached_patterns

    @pytest.mark.asyncio
    async def test_load_patterns_from_database(self, mock_cache):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"id": 1, "phrase": "hello", "emoji": "👋"},
            {"id": 2, "phrase": "world", "emoji": "🌍"},
        ]

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        await matcher.load_patterns(456)
        assert len(matcher._patterns_by_server[456]) == 2

    @pytest.mark.asyncio
    async def test_load_patterns_skips_invalid_regex(self, mock_cache):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"id": 1, "phrase": "hello", "emoji": "👋"},
            {"id": 2, "phrase": "[invalid(regex", "emoji": "❌"},
        ]

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        await matcher.load_patterns(789)
        assert len(matcher._patterns_by_server[789]) == 1

    @pytest.mark.asyncio
    async def test_match_phrases_no_patterns(self, mock_cache):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert await matcher.match_phrases("hello world", 123) == []

    @pytest.mark.asyncio
    async def test_match_phrases_with_match(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [
            PhrasePattern(
                phrase_id="1",
                pattern=re.compile(r"hello", re.IGNORECASE),
                emoji="👋",
                server_id=123,
            )
        ]
        result = await matcher.match_phrases("Hello World!", 123)
        assert len(result) == 1
        assert result[0] == ("1", "👋")

    @pytest.mark.asyncio
    async def test_match_phrases_no_match(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [
            PhrasePattern(
                phrase_id="1",
                pattern=re.compile(r"goodbye", re.IGNORECASE),
                emoji="👋",
                server_id=123,
            )
        ]
        assert await matcher.match_phrases("Hello World!", 123) == []

    @pytest.mark.asyncio
    async def test_match_phrases_multiple_matches(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [
            PhrasePattern(
                phrase_id="1",
                pattern=re.compile(r"hello", re.IGNORECASE),
                emoji="👋",
                server_id=123,
            ),
            PhrasePattern(
                phrase_id="2",
                pattern=re.compile(r"world", re.IGNORECASE),
                emoji="🌍",
                server_id=123,
            ),
        ]
        assert len(await matcher.match_phrases("Hello World!", 123)) == 2

    @pytest.mark.asyncio
    async def test_match_with_timeout(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        result = await matcher._match_with_timeout(re.compile(r"test"), "this is a test")
        assert result is not None
        assert result.group() == "test"

    @pytest.mark.asyncio
    async def test_match_with_timeout_no_match(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert await matcher._match_with_timeout(re.compile(r"missing"), "this is a test") is None

    @pytest.mark.asyncio
    async def test_disable_pattern(self, mock_cache):
        mock_conn = AsyncMock()

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        await matcher._disable_pattern("123")
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_pattern_handles_error(self, mock_cache):
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("Database error")

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        await matcher._disable_pattern("123")


class TestPhraseMatcherValidation:
    @pytest.mark.asyncio
    async def test_validate_pattern_valid(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock):
            await matcher.validate_pattern("hello")

    @pytest.mark.asyncio
    async def test_validate_pattern_too_long(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock) as mock_validate:
            mock_validate.side_effect = RegexValidationError("Pattern exceeds maximum length")
            with pytest.raises(RegexValidationError):
                await matcher.validate_pattern("a" * 501)

    @pytest.mark.asyncio
    async def test_validate_pattern_invalid_syntax(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock):
            with pytest.raises(RegexValidationError) as exc_info:
                await matcher.validate_pattern("[invalid(")
            assert "Invalid regex" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_pattern_redos_check(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock) as mock_validate:
            await matcher.validate_pattern("hello")
            mock_validate.assert_called_once_with("hello")


class TestPhraseMatcherTimeout:
    @pytest.mark.asyncio
    async def test_match_phrases_timeout_disables_pattern(self, mock_cache):
        mock_conn = AsyncMock()

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_db_pool = MagicMock()
        mock_db_pool.acquire = acquire
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [
            PhrasePattern(
                phrase_id="1",
                pattern=re.compile(r"hello", re.IGNORECASE),
                emoji="👋",
                server_id=123,
            )
        ]

        with patch.object(matcher, "_match_with_timeout", new_callable=AsyncMock) as mock_match:
            mock_match.side_effect = asyncio.TimeoutError()
            assert await matcher.match_phrases("Hello World!", 123) == []
            mock_conn.execute.assert_called_once()
