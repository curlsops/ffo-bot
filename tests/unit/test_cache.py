import time

from bot.cache.memory import InMemoryCache


def test_cache_set_get():
    cache = InMemoryCache(max_size=10, default_ttl=60)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_cache_expiration():
    cache = InMemoryCache(max_size=10, default_ttl=1)
    cache.set("key1", "value1", ttl=0.05)
    assert cache.get("key1") == "value1"
    time.sleep(0.1)
    assert cache.get("key1") is None


def test_cache_delete():
    cache = InMemoryCache(max_size=10, default_ttl=60)
    cache.set("key1", "value1")
    cache.delete("key1")
    assert cache.get("key1") is None


def test_cache_clear():
    cache = InMemoryCache(max_size=10, default_ttl=60)
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.clear()
    assert cache.size() == 0


def test_cache_eviction():
    cache = InMemoryCache(max_size=5, default_ttl=60)
    for i in range(5):
        cache.set(f"key{i}", f"value{i}")
    assert cache.size() == 5
    cache.set("key5", "value5")
    assert cache.size() <= 5


def test_cache_evict_oldest_empty_cache():
    cache = InMemoryCache(max_size=5, default_ttl=60)
    cache._evict_oldest()
    assert cache.size() == 0


def test_cache_get_missing_key():
    cache = InMemoryCache(max_size=10, default_ttl=60)
    assert cache.get("nonexistent") is None


def test_cache_delete_nonexistent_key():
    cache = InMemoryCache(max_size=10, default_ttl=60)
    cache.delete("nonexistent")
    assert cache.size() == 0
