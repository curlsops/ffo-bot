from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.processors.phrase_matcher import PhraseMatcher
from bot.utils.regex_validator import RegexValidationError


@pytest.mark.asyncio
async def test_phrase_matcher_simple_match(mock_cache):
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [{"id": "uuid-1", "phrase": r"hello", "emoji": "👋"}]

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
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [{"id": "uuid-1", "phrase": r"test", "emoji": "✅"}]

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_db_pool = MagicMock()
    mock_db_pool.acquire = acquire
    matcher = PhraseMatcher(mock_db_pool, mock_cache)
    await matcher.load_patterns(123456789)

    for message in ["TEST", "Test", "test", "TeSt"]:
        assert len(await matcher.match_phrases(message, 123456789)) == 1


@pytest.mark.asyncio
async def test_validate_dangerous_pattern(mock_db_pool, mock_cache):
    matcher = PhraseMatcher(mock_db_pool, mock_cache)
    with pytest.raises(RegexValidationError):
        await matcher.validate_pattern(r"(a+)+")


@pytest.mark.asyncio
async def test_normalize_message(mock_db_pool, mock_cache):
    matcher = PhraseMatcher(mock_db_pool, mock_cache)
    assert matcher._normalize_message("Hello! World? 123") == "hello world 123"
