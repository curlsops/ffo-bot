"""Database utilities for transient error handling and timeouts."""

import asyncio

import asyncpg

# Exceptions that indicate transient DB unavailability (shutdown, startup, connection lost).
# asyncio.TimeoutError when acquire times out.
# Use when retrying or falling back to cache is appropriate.
TRANSIENT_DB_ERRORS = (
    asyncpg.CannotConnectNowError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.PostgresConnectionError,
    asyncio.TimeoutError,
)
