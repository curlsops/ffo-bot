from datetime import UTC, datetime, timedelta

import pytest

from bot.cache.memory import EVICT_TARGET_RATIO, EVICT_TRIGGER_RATIO, CacheEntry, InMemoryCache


def make_cache(**overrides):
    defaults = {"max_size": 100, "default_ttl": 60, "max_memory_bytes": 0}
    defaults.update(overrides)
    return InMemoryCache(**defaults)


class TestCacheBasics:
    def test_set_get(self):
        cache = make_cache(max_size=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        cache = make_cache(max_size=10)
        assert cache.get("missing") is None

    def test_delete_existing_and_missing(self):
        cache = make_cache(max_size=10)
        cache.set("key1", "value1")
        cache.delete("key1")
        cache.delete("does-not-exist")
        assert cache.get("key1") is None
        assert cache.size() == 0

    def test_clear(self):
        cache = make_cache(max_size=10)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.size() == 0

    def test_overwrite_existing_key_keeps_size_one(self):
        cache = make_cache(max_size=10)
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"
        assert cache.size() == 1


class TestCacheEntryBehavior:
    def test_is_expired_false(self):
        entry = CacheEntry("v", datetime.now(UTC) + timedelta(seconds=60))
        assert entry.is_expired() is False

    def test_is_expired_true(self):
        entry = CacheEntry("v", datetime.now(UTC) - timedelta(seconds=1))
        assert entry.is_expired() is True

    @pytest.mark.parametrize("value", [1, "a", None, [], {}])
    def test_entry_stores_value(self, value):
        entry = CacheEntry(value=value, expires_at=datetime.now(UTC), bytes_estimate=0)
        assert entry.value == value

    @pytest.mark.parametrize("bytes_estimate", [0, 10, 1024])
    def test_entry_stores_bytes_estimate(self, bytes_estimate):
        entry = CacheEntry(value="v", expires_at=datetime.now(UTC), bytes_estimate=bytes_estimate)
        assert entry.bytes_estimate == bytes_estimate


class TestCacheExpiration:
    def test_expiry_with_mocked_time(self):
        now = datetime.now(UTC)
        with pytest.MonkeyPatch.context() as monkeypatch:
            mock_datetime = type(
                "MockDateTime", (), {"now": staticmethod(lambda *_: now), "UTC": UTC}
            )
            monkeypatch.setattr("bot.cache.memory.datetime", mock_datetime)
            cache = make_cache(max_size=10)
            cache.set("key1", "value1", ttl=10)
            assert cache.get("key1") == "value1"

            later = now + timedelta(seconds=15)
            monkeypatch.setattr(
                "bot.cache.memory.datetime",
                type("MockDateTime", (), {"now": staticmethod(lambda *_: later), "UTC": UTC}),
            )
            assert cache.get("key1") is None

    @pytest.mark.parametrize("ttl", [0, -1, -100])
    def test_ttl_zero_or_negative_expires_immediately(self, ttl):
        cache = make_cache(max_size=10)
        cache.set("key1", "value1", ttl=ttl)
        assert cache.get("key1") is None

    @pytest.mark.parametrize("ttl", [1, 60, 3600, 86400])
    def test_positive_ttl_preserves_value(self, ttl):
        cache = make_cache(max_size=10)
        cache.set("k", "v", ttl=ttl)
        assert cache.get("k") == "v"

    def test_prune_expired_on_set(self):
        cache = make_cache(max_size=10)
        cache.set("expired", "v1", ttl=0)
        cache.set("fresh", "v2")
        assert cache.get("expired") is None
        assert cache.get("fresh") == "v2"
        assert cache.size() == 1


class TestCacheEvictionAndOrdering:
    def test_max_size_eviction_removes_oldest(self):
        cache = make_cache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)
        assert cache.get("a") is None
        assert cache.get("d") == 4

    def test_lru_get_refreshes_order(self):
        cache = make_cache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.get("a")
        cache.set("d", 4)
        assert cache.get("b") is None
        assert cache.get("a") == 1

    def test_max_size_zero_still_stores_first_item(self):
        cache = make_cache(max_size=0)
        cache.set("key1", "value1")
        assert cache.size() == 1

    def test_max_size_one_replaces_old_item(self):
        cache = make_cache(max_size=1)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.size() == 1
        assert cache.get("key2") == "value2"

    @pytest.mark.parametrize("max_size", [1, 2, 5, 10, 100, 1000])
    def test_respects_max_size(self, max_size):
        cache = make_cache(max_size=max_size)
        for i in range(max_size + 5):
            cache.set(f"k{i}", i)
        assert cache.size() <= max_size

    @pytest.mark.parametrize("n", [1, 2, 3, 10])
    def test_evicts_oldest_when_over_capacity(self, n):
        cache = make_cache(max_size=n)
        for i in range(n):
            cache.set(f"k{i}", i)
        cache.set("new", "new")
        assert cache.get("k0") is None
        assert cache.get("new") == "new"


class TestCacheMemoryAccounting:
    def test_memory_bytes_tracked(self):
        cache = make_cache(max_size=100, max_memory_bytes=1024)
        cache.set("k", "hello")
        assert cache.memory_bytes() > 0
        cache.delete("k")
        assert cache.memory_bytes() == 0

    def test_clear_resets_memory(self):
        cache = make_cache(max_size=100, max_memory_bytes=1024)
        cache.set("k", "value")
        cache.clear()
        assert cache.size() == 0
        assert cache.memory_bytes() == 0

    def test_memory_limit_eviction(self):
        cache = make_cache(max_size=1000, max_memory_bytes=100)
        item = "x" * 50
        for key in ("a", "b", "c", "d"):
            cache.set(key, item)
        assert cache.size() < 4
        assert cache.memory_bytes() <= 150

    def test_estimate_size_fallback_on_serialize_error(self):
        class BadObj:
            def __str__(self):
                raise ValueError("cannot serialize")

        cache = make_cache(max_size=100, max_memory_bytes=1024)
        cache.set("k", BadObj())
        assert cache.get("k") is not None
        assert cache.memory_bytes() == 1024


class TestCacheInternalHelpers:
    def test_needs_eviction_empty_store_false(self):
        cache = make_cache(max_size=5)
        assert cache._needs_eviction(0) is False

    def test_needs_eviction_under_max_false(self):
        cache = make_cache(max_size=10)
        cache.set("a", 1)
        assert cache._needs_eviction(0) is False

    def test_needs_eviction_at_max_true(self):
        cache = make_cache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache._needs_eviction(0) is True

    def test_needs_eviction_memory_under_limit_false(self):
        cache = make_cache(max_size=100, max_memory_bytes=10000)
        cache.set("a", "x" * 10)
        assert cache._needs_eviction(10) is False

    def test_needs_eviction_memory_over_trigger_true(self):
        cache = make_cache(max_size=100, max_memory_bytes=100)
        cache.set("a", "x" * 50)
        assert cache._needs_eviction(50) is True

    def test_prune_expired_removes_entries_and_updates_bytes(self):
        cache = make_cache(max_size=10, max_memory_bytes=1000)
        cache.set("expired", "x", ttl=0)
        before = cache._total_bytes
        cache._prune_expired()
        assert "expired" not in cache._store
        assert cache._total_bytes < before

    def test_evict_oldest_on_empty_cache_noop(self):
        cache = make_cache(max_size=5)
        cache._evict_oldest()
        assert cache.size() == 0

    def test_evict_oldest_reduces_count(self):
        cache = make_cache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache._evict_oldest()
        assert cache.size() == 2
        assert cache.get("a") is None

    def test_evict_oldest_multiple_times_stays_bounded(self):
        cache = make_cache(max_size=2)
        for i in range(5):
            cache.set(f"k{i}", i)
            cache._evict_oldest()
        assert cache.size() <= 2


class TestCacheParametrizedKeysAndValues:
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
        cache = make_cache()
        cache.set(key, "v")
        assert cache.get(key) == "v"

    @pytest.mark.parametrize(
        "value",
        [
            0,
            1,
            -1,
            2**63 - 1,
            "",
            "x",
            True,
            False,
            None,
            [],
            [1, 2, 3],
            {},
            {"a": 1, "b": [1, 2]},
            (1, 2),
            set(),
        ],
    )
    def test_set_get_value(self, value):
        cache = make_cache()
        cache.set("k", value)
        assert cache.get("k") == value

    @pytest.mark.parametrize("n", [1, 2, 5, 10])
    def test_size_after_n_sets(self, n):
        cache = make_cache(max_size=100)
        for i in range(n):
            cache.set(f"k{i}", i)
        assert cache.size() == n


class TestCacheConstants:
    def test_evict_trigger_ratio_range(self):
        assert 0 < EVICT_TRIGGER_RATIO <= 1

    def test_evict_target_ratio_range(self):
        assert 0 < EVICT_TARGET_RATIO <= 1
