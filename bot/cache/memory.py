import asyncio
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

EVICT_TRIGGER_RATIO = 0.9
EVICT_TARGET_RATIO = 0.7


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime
    bytes_estimate: int = 0

    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at


def _estimate_size(obj: Any) -> int:
    try:
        return len(json.dumps(obj, default=str).encode("utf-8"))
    except Exception:
        return 1024


class InMemoryCache:
    def __init__(
        self,
        max_size: int = 10000,
        default_ttl: int = 300,
        max_memory_bytes: int = 0,
    ):
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.max_memory_bytes = max_memory_bytes
        self._total_bytes = 0
        self._lock = asyncio.Lock()

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            return None
        entry = self._store[key]
        if entry.is_expired():
            self._total_bytes -= entry.bytes_estimate
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None):
        self._prune_expired()
        bytes_estimate = _estimate_size(value) if self.max_memory_bytes > 0 else 0

        if key in self._store:
            self._total_bytes -= self._store[key].bytes_estimate

        while self._needs_eviction(bytes_estimate):
            before = len(self._store)
            self._evict_oldest()
            if len(self._store) == before:
                break

        ttl_seconds = ttl if ttl is not None else self.default_ttl
        entry = CacheEntry(
            value=value,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            bytes_estimate=bytes_estimate,
        )
        self._store[key] = entry
        self._store.move_to_end(key)
        self._total_bytes += bytes_estimate

    def delete(self, key: str):
        if key in self._store:
            self._total_bytes -= self._store[key].bytes_estimate
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()
        self._total_bytes = 0

    def size(self) -> int:
        return len(self._store)

    def memory_bytes(self) -> int:
        return self._total_bytes

    def _needs_eviction(self, bytes_to_add: int = 0) -> bool:
        if not self._store:
            return False
        over_count = len(self._store) >= self.max_size
        if self.max_memory_bytes <= 0:
            return over_count
        projected = self._total_bytes + bytes_to_add
        over_memory = projected >= self.max_memory_bytes * EVICT_TRIGGER_RATIO
        return over_count or over_memory

    def _prune_expired(self):
        now = datetime.now(UTC)
        to_remove = [k for k, e in self._store.items() if now >= e.expires_at]
        for k in to_remove:
            self._total_bytes -= self._store[k].bytes_estimate
            del self._store[k]

    def _evict_oldest(self):
        if not self._store:
            return
        target_bytes = (
            int(self.max_memory_bytes * EVICT_TARGET_RATIO) if self.max_memory_bytes > 0 else 0
        )
        target_count = max(0, int(self.max_size * EVICT_TARGET_RATIO))

        while self._store:
            over_count = len(self._store) >= self.max_size and len(self._store) > target_count
            over_memory = self.max_memory_bytes > 0 and self._total_bytes > target_bytes
            if not over_count and not over_memory:
                break
            key = next(iter(self._store))
            self._total_bytes -= self._store[key].bytes_estimate
            del self._store[key]
