from datetime import UTC, datetime, timedelta

import pytest

from bot.cache.memory import EVICT_TARGET_RATIO, EVICT_TRIGGER_RATIO, CacheEntry, InMemoryCache


class TestInMemoryCache:
    def test_max_size_eviction(self):
        c = InMemoryCache(max_size=3, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.set("d", 4)
        assert c.get("a") is None
        assert c.get("d") == 4

    def test_memory_bytes_tracked(self):
        c = InMemoryCache(max_size=100, default_ttl=60, max_memory_bytes=1024)
        c.set("k", "hello")
        assert c.memory_bytes() > 0
        c.delete("k")
        assert c.memory_bytes() == 0

    def test_memory_limit_eviction(self):
        c = InMemoryCache(max_size=1000, default_ttl=60, max_memory_bytes=100)
        item = "x" * 50
        for key in ("a", "b", "c", "d"):
            c.set(key, item)
        assert c.size() < 4
        assert c.memory_bytes() <= 150

    def test_lru_get_refreshes_order(self):
        c = InMemoryCache(max_size=3, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.get("a")
        c.set("d", 4)
        assert c.get("b") is None
        assert c.get("a") == 1

    def test_clear_resets_memory(self):
        c = InMemoryCache(max_size=100, default_ttl=60, max_memory_bytes=1024)
        c.set("k", "value")
        c.clear()
        assert c.size() == 0
        assert c.memory_bytes() == 0

    def test_estimate_size_fallback_on_serialize_error(self):
        class BadObj:
            def __str__(self):
                raise ValueError("cannot serialize")

        c = InMemoryCache(max_size=100, default_ttl=60, max_memory_bytes=1024)
        c.set("k", BadObj())
        assert c.get("k") is not None
        assert c.memory_bytes() == 1024


class TestCacheEntry:
    def test_is_expired_false(self):
        entry = CacheEntry("v", datetime.now(UTC) + timedelta(seconds=60))
        assert entry.is_expired() is False

    def test_is_expired_true(self):
        entry = CacheEntry("v", datetime.now(UTC) - timedelta(seconds=1))
        assert entry.is_expired() is True

    @pytest.mark.parametrize("val", [1, "a", None, [], {}])
    def test_entry_stores_value(self, val):
        entry = CacheEntry(val, datetime.now(UTC), bytes_estimate=0)
        assert entry.value == val

    @pytest.mark.parametrize("bytes_est", [0, 10, 1024])
    def test_entry_bytes_estimate(self, bytes_est):
        entry = CacheEntry("v", datetime.now(UTC), bytes_estimate=bytes_est)
        assert entry.bytes_estimate == bytes_est


class TestCacheParametrizedKeys:
    @pytest.mark.parametrize(
        "key",
        [
            "k",
            "key",
            "a" * 100,
            "k1",
            "user:123",
            "server:456:channel:789",
            "0",
            "key-with-dash",
            "key_with_underscore",
            "UPPER",
        ],
    )
    def test_set_get_key(self, key):
        c = InMemoryCache(max_size=100, default_ttl=60)
        c.set(key, "v")
        assert c.get(key) == "v"


class TestCacheParametrizedValues:
    @pytest.mark.parametrize(
        "val",
        [
            0,
            1,
            -1,
            2**63 - 1,
            "",
            "x",
            True,
            False,
            [],
            [1, 2, 3],
            {},
            {"a": 1, "b": [1, 2]},
            (1, 2),
            set(),
        ],
    )
    def test_set_get_value(self, val):
        c = InMemoryCache(max_size=100, default_ttl=60)
        c.set("k", val)
        assert c.get("k") == val


class TestCacheParametrizedTtl:
    @pytest.mark.parametrize("ttl", [1, 60, 3600, 86400])
    def test_ttl_preserved_on_set(self, ttl):
        c = InMemoryCache(max_size=100, default_ttl=60)
        c.set("k", "v", ttl=ttl)
        assert c.get("k") == "v"

    @pytest.mark.parametrize("ttl", [0, -1, -100])
    def test_ttl_zero_or_negative_expires(self, ttl):
        c = InMemoryCache(max_size=100, default_ttl=60)
        c.set("k", "v", ttl=ttl)
        assert c.get("k") is None


class TestCacheParametrizedSizes:
    @pytest.mark.parametrize("max_size", [1, 2, 5, 10, 100, 1000])
    def test_respects_max_size(self, max_size):
        c = InMemoryCache(max_size=max_size, default_ttl=60)
        for i in range(max_size + 5):
            c.set(f"k{i}", i)
        assert c.size() <= max_size

    @pytest.mark.parametrize("n", [1, 2, 3, 10])
    def test_evicts_oldest_when_over_capacity(self, n):
        c = InMemoryCache(max_size=n, default_ttl=60)
        for i in range(n):
            c.set(f"k{i}", i)
        c.set("new", "new")
        assert c.get("k0") is None
        assert c.get("new") == "new"


class TestCacheNeedsEviction:
    def test_empty_no_eviction(self):
        c = InMemoryCache(max_size=5, default_ttl=60)
        assert c._needs_eviction(0) is False

    def test_under_max_no_eviction(self):
        c = InMemoryCache(max_size=10, default_ttl=60)
        c.set("a", 1)
        assert c._needs_eviction(0) is False

    def test_at_max_needs_eviction(self):
        c = InMemoryCache(max_size=2, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        assert c._needs_eviction(0) is True

    def test_memory_under_limit_no_eviction(self):
        c = InMemoryCache(max_size=100, default_ttl=60, max_memory_bytes=10000)
        c.set("a", "x" * 10)
        assert c._needs_eviction(10) is False

    def test_memory_over_trigger_needs_eviction(self):
        c = InMemoryCache(max_size=100, default_ttl=60, max_memory_bytes=100)
        c.set("a", "x" * 50)
        assert c._needs_eviction(50) is True


class TestCachePruneExpired:
    def test_prune_removes_expired(self):
        c = InMemoryCache(max_size=10, default_ttl=60)
        c.set("exp", "v", ttl=0)
        c.set("ok", "v2")
        c._prune_expired()
        assert "exp" not in c._store
        assert "ok" in c._store

    def test_prune_updates_total_bytes(self):
        c = InMemoryCache(max_size=10, default_ttl=60, max_memory_bytes=1000)
        c.set("a", "x", ttl=0)
        before = c._total_bytes
        c._prune_expired()
        assert c._total_bytes < before


class TestCacheEvictOldest:
    def test_evict_reduces_count(self):
        c = InMemoryCache(max_size=3, default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c._evict_oldest()
        assert c.size() == 2
        assert c.get("a") is None

    def test_evict_multiple_times(self):
        c = InMemoryCache(max_size=2, default_ttl=60)
        for i in range(5):
            c.set(f"k{i}", i)
            c._evict_oldest()
        assert c.size() <= 2


class TestCacheConstants:
    def test_evict_trigger_ratio(self):
        assert 0 < EVICT_TRIGGER_RATIO <= 1

    def test_evict_target_ratio(self):
        assert 0 < EVICT_TARGET_RATIO <= 1
