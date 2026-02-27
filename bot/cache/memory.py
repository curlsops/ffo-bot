"""In-memory cache implementation."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with expiration."""

    value: Any
    expires_at: datetime

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return datetime.now(UTC) >= self.expires_at


class InMemoryCache:
    """
    Simple in-memory cache with TTL support.

    Thread-safe cache for storing temporary data with automatic expiration.
    """

    def __init__(self, max_size: int = 10000, default_ttl: int = 300):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default TTL in seconds
        """
        self._store: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._lock = asyncio.Lock()

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        if key not in self._store:
            return None

        entry = self._store[key]

        if entry.is_expired():
            del self._store[key]
            return None

        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        if len(self._store) >= self.max_size:
            self._evict_oldest()

        ttl_seconds = ttl if ttl is not None else self.default_ttl
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        self._store[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str):
        """
        Remove key from cache.

        Args:
            key: Cache key to remove
        """
        if key in self._store:
            del self._store[key]

    def clear(self):
        """Clear all cache entries."""
        self._store.clear()
        logger.debug("Cache cleared")

    def size(self) -> int:
        """
        Get current cache size.

        Returns:
            Number of entries in cache
        """
        return len(self._store)

    def _evict_oldest(self):
        """Evict 10% of oldest entries when cache is full."""
        if not self._store:
            return

        # Sort by expiration time and remove oldest 10%
        sorted_keys = sorted(self._store.keys(), key=lambda k: self._store[k].expires_at)

        evict_count = max(1, len(sorted_keys) // 10)

        for key in sorted_keys[:evict_count]:
            del self._store[key]

        logger.debug(f"Evicted {evict_count} cache entries")
