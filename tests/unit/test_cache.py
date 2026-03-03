from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from bot.cache.memory import InMemoryCache


class TestCacheBasics:
    def test_set_get(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        assert cache.get("nonexistent") is None

    def test_delete(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("key1", "value1")
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.delete("nonexistent")
        assert cache.size() == 0

    def test_clear(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.size() == 0

    def test_overwrite_existing_key(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2" and cache.size() == 1


class TestCacheExpiration:
    def test_expiry_with_mocked_time(self):
        now = datetime.now(UTC)
        cache = InMemoryCache(max_size=10, default_ttl=60)

        with patch("bot.cache.memory.datetime") as mock_dt:
            mock_dt.now.return_value = now
            cache.set("key1", "value1", ttl=10)
            assert cache.get("key1") == "value1"

            mock_dt.now.return_value = now + timedelta(seconds=15)
            assert cache.get("key1") is None

    @pytest.mark.parametrize("ttl", [0, -1])
    def test_immediate_expiry(self, ttl):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("key1", "value1", ttl=ttl)
        assert cache.get("key1") is None

    def test_prune_expired_on_set(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("expired", "v1", ttl=0)
        cache.set("fresh", "v2")
        assert cache.get("expired") is None
        assert cache.get("fresh") == "v2"
        assert cache.size() == 1


class TestCacheEviction:
    def test_evicts_when_full(self):
        cache = InMemoryCache(max_size=5, default_ttl=60)
        for i in range(5):
            cache.set(f"key{i}", f"value{i}")
        assert cache.size() == 5
        cache.set("key5", "value5")
        assert cache.size() <= 5

    def test_evict_oldest_empty_cache(self):
        cache = InMemoryCache(max_size=5, default_ttl=60)
        cache._evict_oldest()
        assert cache.size() == 0

    def test_max_size_zero(self):
        cache = InMemoryCache(max_size=0, default_ttl=60)
        cache.set("key1", "value1")
        assert cache.size() == 1

    def test_max_size_one(self):
        cache = InMemoryCache(max_size=1, default_ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.size() == 1


class TestCacheValues:
    def test_none_value(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("key1", None)
        assert cache.get("key1") is None

    def test_complex_values(self):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set("list", [1, 2, 3])
        cache.set("dict", {"a": 1})
        assert cache.get("list") == [1, 2, 3]
        assert cache.get("dict") == {"a": 1}


class TestCacheSizeBoundary:
    def test_size_at_max_still_accepts(self):
        cache = InMemoryCache(max_size=3, default_ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.size() == 3
        cache.set("d", 4)
        assert cache.size() <= 3
        assert cache.get("d") == 4

    @pytest.mark.parametrize("n", [1, 2, 5, 10])
    def test_size_after_n_sets(self, n):
        cache = InMemoryCache(max_size=100, default_ttl=60)
        for i in range(n):
            cache.set(f"k{i}", i)
        assert cache.size() == n

    @pytest.mark.parametrize("key", ["a", "key_with_underscore", "123", "a" * 50])
    def test_various_key_types(self, key):
        cache = InMemoryCache(max_size=10, default_ttl=60)
        cache.set(key, "val")
        assert cache.get(key) == "val"
