"""Test rate limiter."""

import asyncio

import pytest

from bot.utils.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_initial_requests():
    """Test rate limiter allows initial requests."""
    limiter = RateLimiter(user_capacity=10, server_capacity=100)

    allowed, reason = await limiter.check_rate_limit(user_id=123, server_id=456)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limiter_blocks_excessive_requests():
    """Test rate limiter blocks excessive requests."""
    limiter = RateLimiter(user_capacity=2, server_capacity=100)

    # Use up capacity
    await limiter.check_rate_limit(user_id=123, server_id=456)
    await limiter.check_rate_limit(user_id=123, server_id=456)

    # This should be blocked
    allowed, reason = await limiter.check_rate_limit(user_id=123, server_id=456)
    assert allowed is False
    assert "slow down" in reason.lower()


@pytest.mark.asyncio
async def test_rate_limiter_refills_tokens():
    """Test rate limiter refills tokens over time."""
    limiter = RateLimiter(user_capacity=2, user_refill_rate=100.0, server_capacity=100)

    # Use up capacity
    await limiter.check_rate_limit(user_id=123, server_id=456)
    await limiter.check_rate_limit(user_id=123, server_id=456)

    # Wait for refill (0.05 seconds at 100 tokens/sec = 5 tokens)
    await asyncio.sleep(0.05)

    # Should be allowed again
    allowed, reason = await limiter.check_rate_limit(user_id=123, server_id=456)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limiter_server_limit_exceeded():
    """Test rate limiter blocks when server capacity is exceeded."""
    limiter = RateLimiter(user_capacity=100, server_capacity=2, server_refill_rate=0.01)

    # Use up server capacity with different users
    await limiter.check_rate_limit(user_id=1, server_id=456)
    await limiter.check_rate_limit(user_id=2, server_id=456)

    # This should be blocked by server limit
    allowed, reason = await limiter.check_rate_limit(user_id=3, server_id=456)
    assert allowed is False
    assert "server" in reason.lower()
