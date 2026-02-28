"""Rate limiting with token bucket algorithm."""

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter per-user and per-server."""

    def __init__(
        self,
        user_capacity: int = 10,
        user_refill_rate: float = 10 / 60,  # 10 per minute
        server_capacity: int = 100,
        server_refill_rate: float = 100 / 60,  # 100 per minute
    ):
        # user_id -> (tokens, last_refill)
        self._user_buckets: Dict[int, Tuple[float, datetime]] = defaultdict(
            lambda: (user_capacity, datetime.now(UTC))
        )

        # server_id -> (tokens, last_refill)
        self._server_buckets: Dict[int, Tuple[float, datetime]] = defaultdict(
            lambda: (server_capacity, datetime.now(UTC))
        )

        self.user_capacity = user_capacity
        self.user_refill_rate = user_refill_rate
        self.server_capacity = server_capacity
        self.server_refill_rate = server_refill_rate
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, user_id: int, server_id: int) -> Tuple[bool, str]:
        async with self._lock:
            if not self._check_bucket(
                self._user_buckets, user_id, self.user_capacity, self.user_refill_rate
            ):
                return False, "You're sending commands too quickly. Please slow down."

            if not self._check_bucket(
                self._server_buckets, server_id, self.server_capacity, self.server_refill_rate
            ):
                return False, "Server rate limit exceeded. Please try again later."

            self._consume_token(self._user_buckets, user_id)
            self._consume_token(self._server_buckets, server_id)
            return True, ""

    def _check_bucket(self, buckets: Dict, key: int, capacity: float, refill_rate: float) -> bool:
        tokens, last_refill = buckets[key]
        now = datetime.now(UTC)
        new_tokens = min(capacity, tokens + ((now - last_refill).total_seconds() * refill_rate))
        buckets[key] = (new_tokens, now)
        return new_tokens >= 1.0

    def _consume_token(self, buckets: Dict, key: int):
        tokens, last_refill = buckets[key]
        buckets[key] = (tokens - 1.0, last_refill)
