"""Tests for phrase matcher."""

import asyncio
import re
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.processors.phrase_matcher import PhraseMatcher, PhrasePattern
from bot.utils.regex_validator import RegexValidationError


# --- Fixtures ---

@asynccontextmanager
async def _db_ctx(conn):
    yield conn


def _make_db_pool(conn):
    pool = MagicMock()
    pool.acquire = lambda: _db_ctx(conn)
    return pool


def _pattern(phrase_id="1", pattern=r"hello", emoji="👋", server_id=123):
    return PhrasePattern(phrase_id=phrase_id, pattern=re.compile(pattern, re.IGNORECASE), emoji=emoji, server_id=server_id)


# --- PhrasePattern ---

class TestPhrasePattern:
    def test_creation(self):
        p = _pattern()
        assert p.phrase_id == "1" and p.emoji == "👋" and p.server_id == 123


# --- PhraseMatcher Init ---

class TestPhraseMatcherInit:
    def test_initialization(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert matcher.db_pool == mock_db_pool
        assert matcher._patterns_by_server == {}


# --- Normalization ---

class TestNormalization:
    @pytest.mark.parametrize("inp,expected", [
        ("Hello World!", "hello world!"),
        ("Hello, World! How are you?", "hello, world! how are you?"),
        ("Hello @user #channel $money", "hello @user #channel $money"),
        ("Test 123 Message", "test 123 message"),
        ("UPPERCASE MESSAGE", "uppercase message"),
        (":3", ":3"),
        ("UwU :3 OwO", "uwu :3 owo"),
    ])
    def test_normalize_message(self, mock_db_pool, mock_cache, inp, expected):
        assert PhraseMatcher(mock_db_pool, mock_cache)._normalize_message(inp) == expected


# --- Cache Invalidation ---

class TestCacheInvalidation:
    def test_invalidate_cache(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [MagicMock()]
        matcher.invalidate_cache(123)
        assert 123 not in matcher._patterns_by_server

    def test_invalidate_nonexistent(self, mock_db_pool, mock_cache):
        PhraseMatcher(mock_db_pool, mock_cache).invalidate_cache(999)


# --- Pattern Loading ---

class TestPatternLoading:
    @pytest.mark.asyncio
    async def test_from_cache(self, mock_db_pool, mock_cache):
        cached = [_pattern()]
        mock_cache.set("phrase_patterns:123", cached)
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        await matcher.load_patterns(123)
        assert matcher._patterns_by_server[123] == cached

    @pytest.mark.asyncio
    async def test_from_database(self, mock_cache):
        conn = AsyncMock(fetch=AsyncMock(return_value=[
            {"id": 1, "phrase": "hello", "emoji": "👋"},
            {"id": 2, "phrase": "world", "emoji": "🌍"},
        ]))
        matcher = PhraseMatcher(_make_db_pool(conn), mock_cache)
        await matcher.load_patterns(456)
        assert len(matcher._patterns_by_server[456]) == 2

    @pytest.mark.asyncio
    async def test_skips_invalid_regex(self, mock_cache):
        conn = AsyncMock(fetch=AsyncMock(return_value=[
            {"id": 1, "phrase": "hello", "emoji": "👋"},
            {"id": 2, "phrase": "[invalid(regex", "emoji": "❌"},
        ]))
        matcher = PhraseMatcher(_make_db_pool(conn), mock_cache)
        await matcher.load_patterns(789)
        assert len(matcher._patterns_by_server[789]) == 1


# --- Pattern Matching ---

class TestPatternMatching:
    @pytest.mark.asyncio
    async def test_no_patterns(self, mock_cache):
        conn = AsyncMock(fetch=AsyncMock(return_value=[]))
        matcher = PhraseMatcher(_make_db_pool(conn), mock_cache)
        assert await matcher.match_phrases("hello world", 123) == []

    @pytest.mark.asyncio
    async def test_with_match(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [_pattern()]
        result = await matcher.match_phrases("Hello World!", 123)
        assert result == [("1", "👋")]

    @pytest.mark.asyncio
    async def test_no_match(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [_pattern(pattern=r"goodbye")]
        assert await matcher.match_phrases("Hello World!", 123) == []

    @pytest.mark.asyncio
    async def test_multiple_matches(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        matcher._patterns_by_server[123] = [_pattern(), _pattern(phrase_id="2", pattern=r"world", emoji="🌍")]
        assert len(await matcher.match_phrases("Hello World!", 123)) == 2

    @pytest.mark.asyncio
    async def test_match_with_timeout(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        result = await matcher._match_with_timeout(re.compile(r"test"), "this is a test")
        assert result is not None and result.group() == "test"

    @pytest.mark.asyncio
    async def test_match_with_timeout_no_match(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        assert await matcher._match_with_timeout(re.compile(r"missing"), "this is a test") is None


# --- Disable Pattern ---

class TestDisablePattern:
    @pytest.mark.asyncio
    async def test_disable(self, mock_cache):
        conn = AsyncMock()
        matcher = PhraseMatcher(_make_db_pool(conn), mock_cache)
        await matcher._disable_pattern("123")
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_error(self, mock_cache):
        conn = AsyncMock(execute=AsyncMock(side_effect=Exception("Database error")))
        matcher = PhraseMatcher(_make_db_pool(conn), mock_cache)
        await matcher._disable_pattern("123")


# --- Validation ---

class TestValidation:
    @pytest.mark.asyncio
    async def test_valid_pattern(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock):
            await matcher.validate_pattern("hello")

    @pytest.mark.asyncio
    async def test_too_long(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock) as m:
            m.side_effect = RegexValidationError("Pattern exceeds maximum length")
            with pytest.raises(RegexValidationError):
                await matcher.validate_pattern("a" * 501)

    @pytest.mark.asyncio
    async def test_invalid_syntax(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock):
            with pytest.raises(RegexValidationError, match="Invalid regex"):
                await matcher.validate_pattern("[invalid(")

    @pytest.mark.asyncio
    async def test_redos_check(self, mock_db_pool, mock_cache):
        matcher = PhraseMatcher(mock_db_pool, mock_cache)
        with patch.object(matcher.validator, "validate", new_callable=AsyncMock) as m:
            await matcher.validate_pattern("hello")
            m.assert_called_once_with("hello")


# --- Timeout ---

class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_disables_pattern(self, mock_cache):
        conn = AsyncMock()
        matcher = PhraseMatcher(_make_db_pool(conn), mock_cache)
        matcher._patterns_by_server[123] = [_pattern()]

        with patch.object(matcher, "_match_with_timeout", new_callable=AsyncMock) as m:
            m.side_effect = asyncio.TimeoutError()
            assert await matcher.match_phrases("Hello World!", 123) == []
            conn.execute.assert_called_once()
