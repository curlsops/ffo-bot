"""Database connection pool management."""

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    Async PostgreSQL connection pool manager.

    Wraps asyncpg pool with lifecycle management and error handling.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize with existing pool.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

    @classmethod
    async def create(
        cls, database_url: str, min_size: int = 5, max_size: int = 20, command_timeout: float = 60.0
    ) -> "DatabasePool":
        """
        Create new database connection pool.

        Args:
            database_url: PostgreSQL connection URL
            min_size: Minimum pool size
            max_size: Maximum pool size
            command_timeout: Command timeout in seconds

        Returns:
            DatabasePool instance

        Raises:
            Exception: If pool creation fails
        """
        try:
            pool = await asyncpg.create_pool(
                database_url, min_size=min_size, max_size=max_size, command_timeout=command_timeout
            )

            logger.info(
                f"Created database pool (min: {min_size}, max: {max_size}, "
                f"timeout: {command_timeout}s)"
            )

            return cls(pool)

        except Exception as e:
            logger.error(f"Failed to create database pool: {e}", exc_info=True)
            raise

    def acquire(self):
        """
        Acquire connection from pool (context manager).

        Usage:
            async with pool.acquire() as conn:
                result = await conn.fetch("SELECT * FROM users")

        Returns:
            Connection context manager
        """
        return self._pool.acquire()

    async def execute(self, query: str, *args, timeout: Optional[float] = None):
        """
        Execute query and return status.

        Args:
            query: SQL query
            *args: Query parameters
            timeout: Optional timeout override

        Returns:
            Query result status
        """
        async with self.acquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def fetch(self, query: str, *args, timeout: Optional[float] = None):
        """
        Fetch multiple rows.

        Args:
            query: SQL query
            *args: Query parameters
            timeout: Optional timeout override

        Returns:
            List of records
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def fetchrow(self, query: str, *args, timeout: Optional[float] = None):
        """
        Fetch single row.

        Args:
            query: SQL query
            *args: Query parameters
            timeout: Optional timeout override

        Returns:
            Record or None
        """
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def fetchval(self, query: str, *args, timeout: Optional[float] = None):
        """
        Fetch single value.

        Args:
            query: SQL query
            *args: Query parameters
            timeout: Optional timeout override

        Returns:
            Value or None
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)

    async def close(self):
        """Close all connections in pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Database pool closed")
