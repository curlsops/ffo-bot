import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at


class InMemoryCache:
    def __init__(self, max_size: int = 10000, default_ttl: int = 300):
        self._store: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._lock = asyncio.Lock()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        entry = self._store[key]
        if entry.is_expired():
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if len(self._store) >= self.max_size:
            self._evict_oldest()
        ttl_seconds = ttl if ttl is not None else self.default_ttl
        self._store[key] = CacheEntry(
            value=value, expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        )

    def delete(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()

    def size(self) -> int:
        return len(self._store)

    def _evict_oldest(self):
        if not self._store:
            return
        sorted_keys = sorted(self._store.keys(), key=lambda k: self._store[k].expires_at)
        for key in sorted_keys[: max(1, len(sorted_keys) // 10)]:
            del self._store[key]
