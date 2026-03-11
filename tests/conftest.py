import os
import subprocess
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run_alembic(url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


@pytest.fixture(scope="session")
def postgres_container():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:18", driver=None) as postgres:
        yield postgres


@pytest.fixture(scope="session")
def database_url(request):
    url = os.environ.get("DATABASE_URL")
    if url:
        _run_alembic(url)
        return url
    postgres = request.getfixturevalue("postgres_container")
    url = postgres.get_connection_url()
    _run_alembic(url)
    return url


@pytest.fixture
def mock_db_pool():
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
    from bot.cache.memory import InMemoryCache

    return InMemoryCache(max_size=100, default_ttl=60)


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot.is_ready.return_value = True
    bot.guilds = []
    bot.user = MagicMock()
    bot.user.id = 123456789
    bot.user.__str__ = lambda self: "TestBot#1234"
    return bot


@pytest.fixture
def mock_admin_bot(mock_db_pool):
    from tests.helpers import mock_user

    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.permission_checker.invalidate_user_cache = MagicMock()
    bot._register_server = AsyncMock()
    bot.cache = MagicMock()
    bot.cache.get = MagicMock(return_value=None)
    bot.db_pool = mock_db_pool
    bot.fetch_user = AsyncMock(side_effect=lambda uid: mock_user(uid, f"user-{uid}"))
    return bot


@pytest.fixture
def mock_discord_message():
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
    guild = MagicMock()
    guild.id = 111222333
    guild.name = "Test Server"
    guild.members = []
    return guild
