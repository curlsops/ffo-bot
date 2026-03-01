"""Database connection pool management."""

import json
import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


class DatabasePool:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def create(
        cls, database_url: str, min_size: int = 5, max_size: int = 20, command_timeout: float = 60.0
    ) -> "DatabasePool":
        try:
            pool = await asyncpg.create_pool(
                database_url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=command_timeout,
                init=_init_connection,
            )
            return cls(pool)
        except Exception as e:
            logger.error(f"Failed to create pool: {e}", exc_info=True)
            raise

    def acquire(self):
        return self._pool.acquire()

    async def execute(self, query: str, *args, timeout: Optional[float] = None):
        async with self.acquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def fetch(self, query: str, *args, timeout: Optional[float] = None):
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def fetchrow(self, query: str, *args, timeout: Optional[float] = None):
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def fetchval(self, query: str, *args, timeout: Optional[float] = None):
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)

    async def close(self):
        if self._pool:
            await self._pool.close()
