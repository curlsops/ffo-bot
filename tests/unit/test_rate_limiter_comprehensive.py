from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from bot.utils.rate_limiter import RateLimiter


class TestRateLimiterParametrized:
    @pytest.mark.parametrize("user_id", [0, 1, 999, 123456789012345678])
    @pytest.mark.parametrize("server_id", [0, 1, 999, 987654321098765432])
    @pytest.mark.asyncio
    async def test_first_request_allowed(self, user_id, server_id):
        limiter = RateLimiter(user_capacity=1, server_capacity=1)
        allowed, _ = await limiter.check_rate_limit(user_id, server_id)
        assert allowed

    @pytest.mark.parametrize("capacity", [1, 2, 3, 5, 10, 20, 50, 100])
    @pytest.mark.asyncio
    async def test_exactly_capacity_requests_allowed(self, capacity):
        limiter = RateLimiter(user_capacity=capacity, server_capacity=capacity * 2)
        for _ in range(capacity):
            allowed, _ = await limiter.check_rate_limit(1, 1)
            assert allowed
        allowed, _ = await limiter.check_rate_limit(1, 1)
        assert not allowed

    @pytest.mark.parametrize("capacity", [1, 2, 5, 10])
    @pytest.mark.asyncio
    async def test_one_over_capacity_blocked(self, capacity):
        limiter = RateLimiter(user_capacity=capacity, server_capacity=capacity + 10)
        for _ in range(capacity):
            await limiter.check_rate_limit(1, 1)
        allowed, reason = await limiter.check_rate_limit(1, 1)
        assert not allowed
        assert "slow" in reason.lower()

    @pytest.mark.parametrize("user_cap,server_cap", [(1, 1), (1, 10), (10, 1), (5, 5), (100, 100)])
    @pytest.mark.asyncio
    async def test_init_stores_capacity(self, user_cap, server_cap):
        limiter = RateLimiter(user_capacity=user_cap, server_capacity=server_cap)
        assert limiter.user_capacity == user_cap
        assert limiter.server_capacity == server_cap

    @pytest.mark.parametrize("n_users", [2, 3, 5, 10])
    @pytest.mark.asyncio
    async def test_users_independent(self, n_users):
        limiter = RateLimiter(user_capacity=1, server_capacity=n_users * 2)
        for uid in range(n_users):
            allowed, _ = await limiter.check_rate_limit(uid, 1)
            assert allowed
        for uid in range(n_users):
            allowed, _ = await limiter.check_rate_limit(uid, 1)
            assert not allowed

    @pytest.mark.parametrize("n_servers", [2, 3, 5, 10])
    @pytest.mark.asyncio
    async def test_servers_independent(self, n_servers):
        limiter = RateLimiter(user_capacity=n_servers * 2, server_capacity=1)
        for sid in range(n_servers):
            allowed, _ = await limiter.check_rate_limit(1, sid)
            assert allowed
        for sid in range(n_servers):
            allowed, _ = await limiter.check_rate_limit(1, sid)
            assert not allowed


class TestRateLimiterRefill:
    @pytest.mark.parametrize("refill_rate", [1.0, 10.0, 100.0, 1000.0])
    @pytest.mark.asyncio
    async def test_refill_restores_tokens(self, refill_rate):
        now = datetime.now(UTC)
        with patch("bot.utils.rate_limiter.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.UTC = UTC
            limiter = RateLimiter(
                user_capacity=1, user_refill_rate=refill_rate, server_capacity=100
            )
            await limiter.check_rate_limit(1, 1)
            allowed, _ = await limiter.check_rate_limit(1, 1)
            assert not allowed
            mock_dt.now.return_value = now + timedelta(seconds=2.0 / refill_rate)
            allowed, _ = await limiter.check_rate_limit(1, 1)
            assert allowed

    @pytest.mark.parametrize("seconds", [0.01, 0.05, 0.1, 0.5, 1.0])
    @pytest.mark.asyncio
    async def test_refill_after_time(self, seconds):
        now = datetime.now(UTC)
        with patch("bot.utils.rate_limiter.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.UTC = UTC
            limiter = RateLimiter(user_capacity=1, user_refill_rate=100.0, server_capacity=100)
            await limiter.check_rate_limit(1, 1)
            mock_dt.now.return_value = now + timedelta(seconds=seconds)
            allowed, _ = await limiter.check_rate_limit(1, 1)
            assert allowed


class TestRateLimiterMessages:
    @pytest.mark.asyncio
    async def test_user_limit_message(self):
        limiter = RateLimiter(user_capacity=1, server_capacity=100)
        await limiter.check_rate_limit(1, 1)
        _, reason = await limiter.check_rate_limit(1, 1)
        assert "slow" in reason.lower()

    @pytest.mark.asyncio
    async def test_server_limit_message(self):
        limiter = RateLimiter(user_capacity=100, server_capacity=1)
        await limiter.check_rate_limit(1, 1)
        _, reason = await limiter.check_rate_limit(2, 1)
        assert "server" in reason.lower()

    @pytest.mark.asyncio
    async def test_allowed_returns_empty_reason(self):
        limiter = RateLimiter(user_capacity=10, server_capacity=100)
        allowed, reason = await limiter.check_rate_limit(1, 1)
        assert allowed
        assert reason == ""
