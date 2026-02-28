"""Test suite configuration."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db_pool():
    """Mock database pool for testing."""
    conn = MagicMock()
    conn.fetchval = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def mock_cache():
    """Mock cache for testing."""
    from bot.cache.memory import InMemoryCache

    return InMemoryCache(max_size=100, default_ttl=60)


@pytest.fixture
def mock_bot():
    """Mock Discord bot for testing."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot.is_ready.return_value = True
    bot.guilds = []
    bot.user = MagicMock()
    bot.user.id = 123456789
    bot.user.__str__ = lambda self: "TestBot#1234"
    return bot


@pytest.fixture
def mock_discord_message():
    """Mock Discord message for testing."""
    message = MagicMock()
    message.id = 123456789
    message.content = "Test message content"
    message.author = MagicMock()
    message.author.id = 987654321
    message.author.bot = False
    message.guild = MagicMock()
    message.guild.id = 111222333
    message.guild.name = "Test Server"
    message.channel = MagicMock()
    message.channel.id = 444555666
    message.embeds = []
    return message


@pytest.fixture
def mock_discord_guild():
    """Mock Discord guild for testing."""
    guild = MagicMock()
    guild.id = 111222333
    guild.name = "Test Server"
    guild.members = []
    return guild
