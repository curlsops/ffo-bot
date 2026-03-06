import asyncio
import logging

import asyncpg

logger = logging.getLogger(__name__)

TRANSIENT_DB_ERRORS = (
    asyncpg.CannotConnectNowError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.PostgresConnectionError,
    asyncio.TimeoutError,
    ConnectionRefusedError,
)


async def cached_or_fallback(cache, cache_key: str, fetch_fn, ttl: int, to_cache):
    try:
        result = await fetch_fn()
        if cache and (cached_val := to_cache(result)) is not None:
            cache.set(cache_key, cached_val, ttl=ttl)
        return result
    except TRANSIENT_DB_ERRORS:
        if cache:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.warning("DB unavailable, using cache")
                return cached
        raise
