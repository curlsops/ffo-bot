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
