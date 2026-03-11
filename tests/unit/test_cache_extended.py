import pytest

from bot.cache.memory import InMemoryCache


class TestInMemoryCache:
    @pytest.mark.parametrize("key", ["a", "x:1:2", "long_key_" + "x" * 50])
    def test_various_keys(self, key):
        c = InMemoryCache(max_size=100, default_ttl=60)
        c.set(key, "val")
        assert c.get(key) == "val"

    @pytest.mark.parametrize("val", ["str", 123, 0, True, False, None, [1, 2], {"a": 1}])
    def test_various_values(self, val):
        c = InMemoryCache(max_size=100, default_ttl=60)
        c.set("k", val)
        assert c.get("k") == val

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
