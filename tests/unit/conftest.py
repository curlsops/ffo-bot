from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.database_url = "postgresql://test:test@localhost/test"
    s.db_pool_min_size = 1
    s.db_pool_max_size = 5
    s.cache_max_size = 100
    s.cache_max_memory_mb = 0.0
    s.cache_default_ttl = 60
    s.feature_media_download = False
    s.feature_quotebook = False
    s.feature_conversion = False
    s.feature_minecraft_whitelist = False
    s.whitelist_cache_reconcile_interval_hours = 24.0
    s.feature_faq = False
    s.feature_music = False
    s.health_check_port = 8080
    s.health_check_host = "0.0.0.0"
    s.interactions_endpoint_enabled = False
    s.feature_anonymous_post = False
    s.rate_limit_user_capacity = 10
    s.rate_limit_server_capacity = 100
    s.shutdown_timeout_seconds = 5
    s.media_storage_path = "/tmp/media"
    s.clear_commands_on_boot = True
    s.otel_tracing_enabled = False
    s.otel_service_name = None
    s.otel_trace_discord_messages = False
    return s


@pytest.fixture
def bot(mock_settings):
    from bot.client import FFOBot

    return FFOBot(mock_settings)
