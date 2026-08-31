from unittest.mock import MagicMock

from bot.utils.user_preferences import invalidate_opt_out_cache


def test_invalidate_opt_out_cache_with_cache():
    cache = MagicMock()
    invalidate_opt_out_cache(cache, 123, 456)
    cache.delete.assert_called_once_with("opt_out:123:456")


def test_invalidate_opt_out_cache_with_none_skips():
    invalidate_opt_out_cache(None, 123, 456)
