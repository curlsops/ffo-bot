"""Integration tests for phrase matching."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.processors.phrase_matcher import PhraseMatcher
from bot.utils.regex_validator import RegexValidationError


@pytest.mark.asyncio
async def test_phrase_matcher_simple_match(mock_cache):
    """Test simple phrase matching."""
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {"id": "uuid-1", "phrase": r"hello", "emoji": "👋"},
    ]

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire

    matcher = PhraseMatcher(mock_db_pool, mock_cache)
    await matcher.load_patterns(123456789)

    matches = await matcher.match_phrases("Hello world!", 123456789)

    assert len(matches) == 1
    assert matches[0][1] == "👋"


@pytest.mark.asyncio
async def test_phrase_matcher_case_insensitive(mock_cache):
    """Test case-insensitive matching."""
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {"id": "uuid-1", "phrase": r"test", "emoji": "✅"},
    ]

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire

    matcher = PhraseMatcher(mock_db_pool, mock_cache)
    await matcher.load_patterns(123456789)

    for message in ["TEST", "Test", "test", "TeSt"]:
        matches = await matcher.match_phrases(message, 123456789)
        assert len(matches) == 1


@pytest.mark.asyncio
async def test_validate_dangerous_pattern(mock_db_pool, mock_cache):
    """Test ReDoS pattern rejection."""
    matcher = PhraseMatcher(mock_db_pool, mock_cache)

    dangerous_pattern = r"(a+)+"

    with pytest.raises(RegexValidationError):
        await matcher.validate_pattern(dangerous_pattern)


@pytest.mark.asyncio
async def test_normalize_message(mock_db_pool, mock_cache):
    """Test message normalization."""
    matcher = PhraseMatcher(mock_db_pool, mock_cache)

    message = "Hello! World? 123"
    normalized = matcher._normalize_message(message)
    assert normalized == "hello world 123"
