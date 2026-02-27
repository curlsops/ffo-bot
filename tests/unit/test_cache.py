"""Test cache functionality."""

from bot.cache.memory import InMemoryCache


def test_cache_set_get():
    """Test basic cache operations."""
    cache = InMemoryCache(max_size=10, default_ttl=60)

    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_cache_expiration():
    """Test cache expiration."""
    cache = InMemoryCache(max_size=10, default_ttl=1)

    cache.set("key1", "value1", ttl=0.05)
    assert cache.get("key1") == "value1"

    # Wait for expiration
    import time

    time.sleep(0.1)

    assert cache.get("key1") is None


def test_cache_delete():
    """Test cache deletion."""
    cache = InMemoryCache(max_size=10, default_ttl=60)

    cache.set("key1", "value1")
    cache.delete("key1")
    assert cache.get("key1") is None


def test_cache_clear():
    """Test cache clear."""
    cache = InMemoryCache(max_size=10, default_ttl=60)

    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.clear()

    assert cache.size() == 0


def test_cache_eviction():
    """Test cache eviction when full."""
    cache = InMemoryCache(max_size=5, default_ttl=60)

    # Fill cache
    for i in range(5):
        cache.set(f"key{i}", f"value{i}")

    assert cache.size() == 5

    # Adding one more should trigger eviction
    cache.set("key5", "value5")

    # Size should still be within limits
    assert cache.size() <= 5


def test_cache_evict_oldest_empty_cache():
    """Test _evict_oldest on empty cache does nothing."""
    cache = InMemoryCache(max_size=5, default_ttl=60)
    cache._evict_oldest()
    assert cache.size() == 0


def test_cache_get_missing_key():
    """Test getting a key that doesn't exist."""
    cache = InMemoryCache(max_size=10, default_ttl=60)
    assert cache.get("nonexistent") is None


def test_cache_delete_nonexistent_key():
    """Test deleting a key that doesn't exist."""
    cache = InMemoryCache(max_size=10, default_ttl=60)
    cache.delete("nonexistent")
    assert cache.size() == 0
