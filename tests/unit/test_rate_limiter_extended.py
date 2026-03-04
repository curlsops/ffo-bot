import pytest

from bot.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_reason_contains_server_when_server_limited(self):
        limiter = RateLimiter(user_capacity=100, server_capacity=2)
        await limiter.check_rate_limit(1, 1)
        await limiter.check_rate_limit(2, 1)
        allowed, reason = await limiter.check_rate_limit(3, 1)
        assert not allowed
        assert "server" in reason.lower()

    @pytest.mark.asyncio
    async def test_reason_contains_slow_when_user_limited(self):
        limiter = RateLimiter(user_capacity=1, server_capacity=100)
        await limiter.check_rate_limit(1, 1)
        allowed, reason = await limiter.check_rate_limit(1, 1)
        assert not allowed
        assert "slow" in reason.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("user_id,server_id", [(1, 1), (999, 888), (0, 0)])
    async def test_first_request_always_allowed(self, user_id, server_id):
        limiter = RateLimiter(user_capacity=1, server_capacity=1)
        allowed, _ = await limiter.check_rate_limit(user_id, server_id)
        assert allowed

    @pytest.mark.asyncio
    async def test_concurrent_users_different_servers(self):
        limiter = RateLimiter(user_capacity=10, server_capacity=20)
        for uid in range(5):
            for sid in range(3):
                allowed, _ = await limiter.check_rate_limit(uid, sid)
                assert allowed
