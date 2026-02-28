import asyncio

import pytest

from bot.utils.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_initial_requests():
    limiter = RateLimiter(user_capacity=10, server_capacity=100)
    allowed, _ = await limiter.check_rate_limit(user_id=123, server_id=456)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limiter_blocks_excessive_requests():
    limiter = RateLimiter(user_capacity=2, server_capacity=100)
    await limiter.check_rate_limit(user_id=123, server_id=456)
    await limiter.check_rate_limit(user_id=123, server_id=456)
    allowed, reason = await limiter.check_rate_limit(user_id=123, server_id=456)
    assert allowed is False
    assert "slow down" in reason.lower()


@pytest.mark.asyncio
async def test_rate_limiter_refills_tokens():
    limiter = RateLimiter(user_capacity=2, user_refill_rate=100.0, server_capacity=100)
    await limiter.check_rate_limit(user_id=123, server_id=456)
    await limiter.check_rate_limit(user_id=123, server_id=456)
    await asyncio.sleep(0.05)
    allowed, _ = await limiter.check_rate_limit(user_id=123, server_id=456)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limiter_server_limit_exceeded():
    limiter = RateLimiter(user_capacity=100, server_capacity=2, server_refill_rate=0.01)
    await limiter.check_rate_limit(user_id=1, server_id=456)
    await limiter.check_rate_limit(user_id=2, server_id=456)
    allowed, reason = await limiter.check_rate_limit(user_id=3, server_id=456)
    assert allowed is False
    assert "server" in reason.lower()
