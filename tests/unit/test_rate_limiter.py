from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from bot.utils.rate_limiter import RateLimiter


def make_limiter(**overrides):
    defaults = {
        "user_capacity": 10,
        "user_refill_rate": 10 / 60,
        "server_capacity": 100,
        "server_refill_rate": 100 / 60,
    }
    defaults.update(overrides)
    return RateLimiter(**defaults)


@pytest.mark.parametrize("user_cap,server_cap", [(1, 1), (1, 10), (5, 50), (100, 1000)])
def test_init_stores_capacity(user_cap, server_cap):
    limiter = make_limiter(user_capacity=user_cap, server_capacity=server_cap)
    assert limiter.user_capacity == user_cap
    assert limiter.server_capacity == server_cap


@pytest.mark.parametrize("user_id", [0, 1, 999, 123456789012345678])
@pytest.mark.parametrize("server_id", [0, 1, 999, 987654321098765432])
@pytest.mark.asyncio
async def test_first_request_allowed(user_id, server_id):
    limiter = make_limiter(user_capacity=1, server_capacity=1)
    allowed, reason = await limiter.check_rate_limit(user_id, server_id)
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_blocks_excessive_user_requests_with_slow_down_reason():
    limiter = make_limiter(user_capacity=2)
    await limiter.check_rate_limit(1, 1)
    await limiter.check_rate_limit(1, 1)
    allowed, reason = await limiter.check_rate_limit(1, 1)
    assert allowed is False
    assert "slow" in reason.lower()


@pytest.mark.asyncio
async def test_server_limit_exceeded_reason_mentions_server():
    limiter = make_limiter(user_capacity=100, server_capacity=2, server_refill_rate=0.01)
    await limiter.check_rate_limit(1, 1)
    await limiter.check_rate_limit(2, 1)
    allowed, reason = await limiter.check_rate_limit(3, 1)
    assert allowed is False
    assert "server" in reason.lower()


@pytest.mark.parametrize("capacity", [1, 2, 3, 5, 10, 20, 50, 100])
@pytest.mark.asyncio
async def test_exactly_capacity_requests_allowed_and_next_is_blocked(capacity):
    limiter = make_limiter(user_capacity=capacity, server_capacity=capacity * 2)
    for _ in range(capacity):
        allowed, _ = await limiter.check_rate_limit(1, 1)
        assert allowed is True
    allowed, reason = await limiter.check_rate_limit(1, 1)
    assert allowed is False
    assert "slow" in reason.lower()


@pytest.mark.asyncio
async def test_zero_user_capacity_blocks_first_request():
    limiter = make_limiter(user_capacity=0)
    allowed, _ = await limiter.check_rate_limit(1, 1)
    assert allowed is False


@pytest.mark.parametrize("n_users", [2, 3, 5, 10])
@pytest.mark.asyncio
async def test_users_are_independent(n_users):
    limiter = make_limiter(user_capacity=1, server_capacity=n_users * 2)
    for uid in range(n_users):
        allowed, _ = await limiter.check_rate_limit(uid, 1)
        assert allowed is True
    for uid in range(n_users):
        allowed, _ = await limiter.check_rate_limit(uid, 1)
        assert allowed is False


@pytest.mark.parametrize("n_servers", [2, 3, 5, 10])
@pytest.mark.asyncio
async def test_servers_are_independent(n_servers):
    limiter = make_limiter(user_capacity=n_servers * 2, server_capacity=1)
    for sid in range(n_servers):
        allowed, _ = await limiter.check_rate_limit(1, sid)
        assert allowed is True
    for sid in range(n_servers):
        allowed, _ = await limiter.check_rate_limit(1, sid)
        assert allowed is False


@pytest.mark.asyncio
async def test_concurrent_users_different_servers_allowed_initially():
    limiter = make_limiter(user_capacity=10, server_capacity=20)
    for uid in range(5):
        for sid in range(3):
            allowed, _ = await limiter.check_rate_limit(uid, sid)
            assert allowed is True


@pytest.mark.parametrize("refill_rate", [1.0, 10.0, 100.0, 1000.0])
@pytest.mark.asyncio
async def test_refill_restores_tokens(refill_rate):
    now = datetime.now(UTC)
    with patch("bot.utils.rate_limiter.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.UTC = UTC
        limiter = make_limiter(user_capacity=1, user_refill_rate=refill_rate)
        await limiter.check_rate_limit(1, 1)
        allowed, _ = await limiter.check_rate_limit(1, 1)
        assert allowed is False

        mock_dt.now.return_value = now + timedelta(seconds=2.0 / refill_rate)
        allowed, _ = await limiter.check_rate_limit(1, 1)
        assert allowed is True


@pytest.mark.parametrize("seconds", [0.01, 0.05, 0.1, 0.5, 1.0])
@pytest.mark.asyncio
async def test_refill_after_elapsed_time(seconds):
    now = datetime.now(UTC)
    with patch("bot.utils.rate_limiter.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.UTC = UTC
        limiter = make_limiter(user_capacity=1, user_refill_rate=100.0)
        await limiter.check_rate_limit(1, 1)
        mock_dt.now.return_value = now + timedelta(seconds=seconds)
        allowed, _ = await limiter.check_rate_limit(1, 1)
        assert allowed is True


@pytest.mark.asyncio
async def test_prunes_stale_full_buckets():
    now = datetime.now(UTC)
    with patch("bot.utils.rate_limiter.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.UTC = UTC
        limiter = make_limiter(
            user_capacity=2,
            user_refill_rate=1.0,
            server_capacity=2,
            server_refill_rate=1.0,
        )
        await limiter.check_rate_limit(1, 1)
        await limiter.check_rate_limit(2, 2)
        assert set(limiter._user_buckets) == {1, 2}
        assert set(limiter._server_buckets) == {1, 2}

        mock_dt.now.return_value = now + timedelta(seconds=301)
        allowed, _ = await limiter.check_rate_limit(99, 99)
        assert allowed is True
        assert set(limiter._user_buckets) == {99}
        assert set(limiter._server_buckets) == {99}


@pytest.mark.asyncio
async def test_does_not_prune_non_refilling_depleted_bucket():
    now = datetime.now(UTC)
    with patch("bot.utils.rate_limiter.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.UTC = UTC
        limiter = make_limiter(
            user_capacity=1,
            user_refill_rate=0.0,
            server_capacity=100,
            server_refill_rate=1000.0,
        )
        await limiter.check_rate_limit(7, 1)

        mock_dt.now.return_value = now + timedelta(seconds=301)
        await limiter.check_rate_limit(8, 1)

        allowed, reason = await limiter.check_rate_limit(7, 1)
        assert allowed is False
        assert "slow" in reason.lower()


def test_can_prune_bucket_false_when_not_idle_long_enough():
    limiter = make_limiter()
    now = datetime.now(UTC)
    last_refill = now - timedelta(seconds=10)
    can_prune = limiter._can_prune_bucket(
        tokens=limiter.user_capacity,
        last_refill=last_refill,
        capacity=limiter.user_capacity,
        refill_rate=limiter.user_refill_rate,
        now=now,
    )
    assert can_prune is False


@pytest.mark.parametrize(
    ("tokens", "capacity", "refill_rate", "expected"),
    [
        (1.0, 1.0, 0.0, True),
        (0.0, 1.0, 0.0, False),
    ],
)
def test_can_prune_bucket_with_non_refilling_rate(tokens, capacity, refill_rate, expected):
    limiter = make_limiter()
    now = datetime.now(UTC)
    last_refill = now - timedelta(seconds=301)
    can_prune = limiter._can_prune_bucket(
        tokens=tokens,
        last_refill=last_refill,
        capacity=capacity,
        refill_rate=refill_rate,
        now=now,
    )
    assert can_prune is expected
