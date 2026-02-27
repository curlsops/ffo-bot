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
        """
        Initialize rate limiter.

        Args:
            user_capacity: Maximum tokens per user
            user_refill_rate: Tokens refilled per second
            server_capacity: Maximum tokens per server
            server_refill_rate: Tokens refilled per second
        """
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
        """
        Check if request is within rate limits.

        Args:
            user_id: Discord user ID
            server_id: Discord server ID

        Returns:
            (allowed, reason) tuple
        """
        async with self._lock:
            # Check user rate limit
            user_allowed = self._check_bucket(
                self._user_buckets, user_id, self.user_capacity, self.user_refill_rate
            )

            if not user_allowed:
                logger.warning(f"User {user_id} rate limited")
                return False, "You're sending commands too quickly. Please slow down."

            # Check server rate limit
            server_allowed = self._check_bucket(
                self._server_buckets, server_id, self.server_capacity, self.server_refill_rate
            )

            if not server_allowed:
                logger.warning(f"Server {server_id} rate limited")
                return False, "Server rate limit exceeded. Please try again later."

            # Consume tokens
            self._consume_token(self._user_buckets, user_id)
            self._consume_token(self._server_buckets, server_id)

            return True, ""

    def _check_bucket(self, buckets: Dict, key: int, capacity: float, refill_rate: float) -> bool:
        """Check if bucket has available tokens."""
        tokens, last_refill = buckets[key]

        # Refill tokens based on time elapsed
        now = datetime.now(UTC)
        elapsed_seconds = (now - last_refill).total_seconds()
        new_tokens = min(capacity, tokens + (elapsed_seconds * refill_rate))

        buckets[key] = (new_tokens, now)

        return new_tokens >= 1.0

    def _consume_token(self, buckets: Dict, key: int):
        """Consume one token from bucket."""
        tokens, last_refill = buckets[key]
        buckets[key] = (tokens - 1.0, last_refill)
