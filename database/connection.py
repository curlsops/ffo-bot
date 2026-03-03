import json
import logging
import time
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


def _query_type(query: str) -> str:
    first = query.strip().split()[0].upper() if query.strip() else "other"
    return first if first in ("SELECT", "INSERT", "UPDATE", "DELETE") else "other"


class _MetricsConnection:
    def __init__(self, conn: asyncpg.Connection, pool: "DatabasePool"):
        self._conn = conn
        self._pool = pool

    def __getattr__(self, name):
        return getattr(self._conn, name)

    async def execute(self, query: str, *args, timeout=None):
        start = time.perf_counter()
        try:
            return await self._conn.execute(query, *args, timeout=timeout)
        finally:
            self._pool._record_duration(_query_type(query), time.perf_counter() - start)

    async def fetch(self, query: str, *args, timeout=None):
        start = time.perf_counter()
        try:
            return await self._conn.fetch(query, *args, timeout=timeout)
        finally:
            self._pool._record_duration(_query_type(query), time.perf_counter() - start)

    async def fetchrow(self, query: str, *args, timeout=None):
        start = time.perf_counter()
        try:
            return await self._conn.fetchrow(query, *args, timeout=timeout)
        finally:
            self._pool._record_duration(_query_type(query), time.perf_counter() - start)

    async def fetchval(self, query: str, *args, timeout=None):
        start = time.perf_counter()
        try:
            return await self._conn.fetchval(query, *args, timeout=timeout)
        finally:
            self._pool._record_duration(_query_type(query), time.perf_counter() - start)

    async def executemany(self, query: str, args, timeout=None):
        start = time.perf_counter()
        try:
            return await self._conn.executemany(query, args, timeout=timeout)
        finally:
            self._pool._record_duration(_query_type(query), time.perf_counter() - start)


class _MetricsAcquireContext:
    def __init__(self, raw_cm, pool: "DatabasePool"):
        self._raw_cm = raw_cm
        self._pool = pool

    async def __aenter__(self):
        conn = await self._raw_cm.__aenter__()
        return _MetricsConnection(conn, self._pool)

    async def __aexit__(self, *args):
        return await self._raw_cm.__aexit__(*args)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


class DatabasePool:
    def __init__(self, pool: asyncpg.Pool, acquire_timeout: float = 5.0, metrics=None):
        self._pool = pool
        self._acquire_timeout = acquire_timeout
        self._metrics = metrics

    def acquire(self, timeout: float | None = None):
        t = timeout if timeout is not None else self._acquire_timeout
        raw_cm = self._pool.acquire(timeout=t)
        return _MetricsAcquireContext(raw_cm, self) if self._metrics else raw_cm

    @classmethod
    async def create(
        cls,
        database_url: str,
        min_size: int = 5,
        max_size: int = 20,
        command_timeout: float = 60.0,
        connection_timeout: float = 10.0,
        acquire_timeout: float = 5.0,
        metrics=None,
    ) -> "DatabasePool":
        try:
            pool = await asyncpg.create_pool(
                database_url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=command_timeout,
                timeout=connection_timeout,
                init=_init_connection,
            )
            return cls(pool, acquire_timeout=acquire_timeout, metrics=metrics)
        except Exception as e:
            logger.error("Failed to create pool: %s", e, exc_info=True)
            raise

    def _record_duration(self, query_type: str, duration: float) -> None:
        if self._metrics and hasattr(self._metrics, "db_query_duration"):
            self._metrics.db_query_duration.labels(query_type=query_type).observe(duration)

    async def execute(self, query: str, *args, timeout: Optional[float] = None):
        start = time.perf_counter()
        try:
            async with self.acquire() as conn:
                return await conn.execute(query, *args, timeout=timeout)
        finally:
            self._record_duration(_query_type(query), time.perf_counter() - start)

    async def fetch(self, query: str, *args, timeout: Optional[float] = None):
        start = time.perf_counter()
        try:
            async with self.acquire() as conn:
                return await conn.fetch(query, *args, timeout=timeout)
        finally:
            self._record_duration(_query_type(query), time.perf_counter() - start)

    async def fetchrow(self, query: str, *args, timeout: Optional[float] = None):
        start = time.perf_counter()
        try:
            async with self.acquire() as conn:
                return await conn.fetchrow(query, *args, timeout=timeout)
        finally:
            self._record_duration(_query_type(query), time.perf_counter() - start)

    async def fetchval(self, query: str, *args, timeout: Optional[float] = None):
        start = time.perf_counter()
        try:
            async with self.acquire() as conn:
                return await conn.fetchval(query, *args, timeout=timeout)
        finally:
            self._record_duration(_query_type(query), time.perf_counter() - start)

    async def close(self):
        if self._pool:
            await self._pool.close()
