"""Tests for rate limiter."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from bot.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_initial_requests(self):
        limiter = RateLimiter(user_capacity=10, server_capacity=100)
        allowed, _ = await limiter.check_rate_limit(user_id=123, server_id=456)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_excessive_requests(self):
        limiter = RateLimiter(user_capacity=2, server_capacity=100)
        await limiter.check_rate_limit(user_id=123, server_id=456)
        await limiter.check_rate_limit(user_id=123, server_id=456)
        allowed, reason = await limiter.check_rate_limit(user_id=123, server_id=456)
        assert allowed is False and "slow down" in reason.lower()

    @pytest.mark.asyncio
    async def test_refills_tokens_with_mocked_time(self):
        now = datetime.now(UTC)
        with patch("bot.utils.rate_limiter.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.UTC = UTC
            limiter = RateLimiter(user_capacity=2, user_refill_rate=100.0, server_capacity=100)
            await limiter.check_rate_limit(user_id=123, server_id=456)
            await limiter.check_rate_limit(user_id=123, server_id=456)

            mock_dt.now.return_value = now + timedelta(seconds=0.05)
            allowed, _ = await limiter.check_rate_limit(user_id=123, server_id=456)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_server_limit_exceeded(self):
        limiter = RateLimiter(user_capacity=100, server_capacity=2, server_refill_rate=0.01)
        await limiter.check_rate_limit(user_id=1, server_id=456)
        await limiter.check_rate_limit(user_id=2, server_id=456)
        allowed, reason = await limiter.check_rate_limit(user_id=3, server_id=456)
        assert allowed is False and "server" in reason.lower()

    @pytest.mark.asyncio
    async def test_different_users_independent(self):
        limiter = RateLimiter(user_capacity=2, server_capacity=100)
        await limiter.check_rate_limit(user_id=1, server_id=456)
        await limiter.check_rate_limit(user_id=1, server_id=456)
        allowed, _ = await limiter.check_rate_limit(user_id=2, server_id=456)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_different_servers_independent(self):
        limiter = RateLimiter(user_capacity=100, server_capacity=2)
        await limiter.check_rate_limit(user_id=1, server_id=456)
        await limiter.check_rate_limit(user_id=1, server_id=456)
        allowed, _ = await limiter.check_rate_limit(user_id=1, server_id=789)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_zero_capacity(self):
        limiter = RateLimiter(user_capacity=0, server_capacity=100)
        allowed, _ = await limiter.check_rate_limit(user_id=123, server_id=456)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_high_refill_rate_with_mocked_time(self):
        now = datetime.now(UTC)
        with patch("bot.utils.rate_limiter.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.UTC = UTC
            limiter = RateLimiter(user_capacity=1, user_refill_rate=1000.0, server_capacity=100)
            await limiter.check_rate_limit(user_id=123, server_id=456)

            mock_dt.now.return_value = now + timedelta(seconds=0.01)
            allowed, _ = await limiter.check_rate_limit(user_id=123, server_id=456)
            assert allowed is True
