import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(
        self,
        user_capacity: int = 10,
        user_refill_rate: float = 10 / 60,
        server_capacity: int = 100,
        server_refill_rate: float = 100 / 60,
    ):
        self._user_buckets: dict[int, tuple[float, datetime]] = defaultdict(
            lambda: (user_capacity, datetime.now(UTC))
        )

        self._server_buckets: dict[int, tuple[float, datetime]] = defaultdict(
            lambda: (server_capacity, datetime.now(UTC))
        )

        self.user_capacity = user_capacity
        self.user_refill_rate = user_refill_rate
        self.server_capacity = server_capacity
        self.server_refill_rate = server_refill_rate
        self._lock = asyncio.Lock()
        self._idle_prune_after_seconds = 300.0
        self._prune_interval_seconds = 60.0
        self._next_prune_at = datetime.now(UTC) + timedelta(seconds=self._prune_interval_seconds)

    async def check_rate_limit(self, user_id: int, server_id: int) -> tuple[bool, str]:
        async with self._lock:
            now = datetime.now(UTC)
            self._maybe_prune_stale_buckets(now)
            if not self._check_bucket(
                self._user_buckets, user_id, self.user_capacity, self.user_refill_rate, now
            ):
                return False, "You're sending commands too quickly. Please slow down."

            if not self._check_bucket(
                self._server_buckets, server_id, self.server_capacity, self.server_refill_rate, now
            ):
                return False, "Server rate limit exceeded. Please try again later."

            self._consume_token(self._user_buckets, user_id)
            self._consume_token(self._server_buckets, server_id)
            return True, ""

    def _check_bucket(
        self,
        buckets: dict,
        key: int,
        capacity: float,
        refill_rate: float,
        now: datetime,
    ) -> bool:
        tokens, last_refill = buckets[key]
        elapsed_seconds = max(0.0, (now - last_refill).total_seconds())
        new_tokens = min(capacity, tokens + (elapsed_seconds * refill_rate))
        buckets[key] = (new_tokens, now)
        return bool(new_tokens >= 1.0)

    def _consume_token(self, buckets: dict, key: int):
        tokens, last_refill = buckets[key]
        buckets[key] = (tokens - 1.0, last_refill)

    def _maybe_prune_stale_buckets(self, now: datetime) -> None:
        if now < self._next_prune_at:
            return

        self._prune_stale_bucket_map(
            self._user_buckets, self.user_capacity, self.user_refill_rate, now
        )
        self._prune_stale_bucket_map(
            self._server_buckets, self.server_capacity, self.server_refill_rate, now
        )
        self._next_prune_at = now + timedelta(seconds=self._prune_interval_seconds)

    def _prune_stale_bucket_map(
        self,
        buckets: dict[int, tuple[float, datetime]],
        capacity: float,
        refill_rate: float,
        now: datetime,
    ) -> None:
        stale_keys: list[int] = []
        for key, (tokens, last_refill) in buckets.items():
            if self._can_prune_bucket(tokens, last_refill, capacity, refill_rate, now):
                stale_keys.append(key)
        for key in stale_keys:
            del buckets[key]

    def _can_prune_bucket(
        self,
        tokens: float,
        last_refill: datetime,
        capacity: float,
        refill_rate: float,
        now: datetime,
    ) -> bool:
        elapsed = (now - last_refill).total_seconds()
        if elapsed < self._idle_prune_after_seconds:
            return False

        if refill_rate <= 0:
            return tokens >= capacity

        missing_tokens = max(0.0, capacity - tokens)
        time_to_full = missing_tokens / refill_rate
        return elapsed >= time_to_full
