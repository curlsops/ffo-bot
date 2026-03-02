import json
import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


class DatabasePool:
    def __init__(self, pool: asyncpg.Pool, acquire_timeout: float = 5.0):
        self._pool = pool
        self._acquire_timeout = acquire_timeout

    def acquire(self, timeout: float | None = None):
        t = timeout if timeout is not None else self._acquire_timeout
        return self._pool.acquire(timeout=t)

    @classmethod
    async def create(
        cls,
        database_url: str,
        min_size: int = 5,
        max_size: int = 20,
        command_timeout: float = 60.0,
        connection_timeout: float = 10.0,
        acquire_timeout: float = 5.0,
    ) -> "DatabasePool":
        try:
            pool = await asyncpg.create_pool(
                database_url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=command_timeout,
                init=_init_connection,
                connect_kwargs={"timeout": connection_timeout},
            )
            return cls(pool, acquire_timeout=acquire_timeout)
        except Exception as e:
            logger.error(f"Failed to create pool: {e}", exc_info=True)
            raise

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
