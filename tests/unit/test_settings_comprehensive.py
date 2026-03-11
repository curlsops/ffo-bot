import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from config.settings import Settings


def _env(tmpdir, **overrides):
    base = {
        "DISCORD_BOT_TOKEN": "t",
        "DISCORD_PUBLIC_KEY": "k",
        "DATABASE_URL": "postgresql://u:p@localhost/db",
        "MEDIA_STORAGE_PATH": tmpdir,
    }
    base.update(overrides)
    return base


class TestSettingsFieldDefaults:
    @pytest.mark.parametrize(
        "field,expected",
        [
            ("environment", "production"),
            ("db_port", 5432),
            ("db_pool_min_size", 5),
            ("db_pool_max_size", 20),
            ("cache_max_size", 10000),
            ("cache_default_ttl", 86400),
            ("rate_limit_user_capacity", 10),
            ("rate_limit_server_capacity", 100),
            ("health_check_port", 8080),
            ("shutdown_timeout_seconds", 30),
            ("media_max_file_size", 104857600),
            ("feature_media_download", True),
            ("feature_reaction_roles", True),
            ("feature_giveaways", True),
            ("feature_quotebook", True),
            ("feature_faq", True),
            ("feature_notify_moderation", True),
            ("feature_rotating_status", False),
            ("feature_voice_transcription", False),
            ("feature_conversion", False),
            ("feature_minecraft_whitelist", False),
            ("feature_anonymous_post", False),
            ("feature_music", False),
        ],
    )
    def test_default(self, field, expected):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, _env(tmpdir), clear=True):
                s = Settings()
                assert getattr(s, field) == expected


class TestSettingsLogLevels:
    @pytest.mark.parametrize(
        "level,expected",
        [
            ("DEBUG", "DEBUG"),
            ("INFO", "INFO"),
            ("debug", "DEBUG"),
            ("info", "INFO"),
        ],
    )
    def test_log_level(self, level, expected):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, _env(tmpdir, LOG_LEVEL=level), clear=True):
                assert Settings().log_level == expected


class TestSettingsLogFormat:
    @pytest.mark.parametrize(
        "fmt,expected",
        [("json", "json"), ("text", "text"), ("JSON", "json"), ("TEXT", "text")],
    )
    def test_log_format(self, fmt, expected):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, _env(tmpdir, LOG_FORMAT=fmt), clear=True):
                assert Settings().log_format == expected


class TestSettingsDatabaseUrl:
    @pytest.mark.parametrize("port", [5432, 5433, 3306])
    def test_db_port_in_url(self, port):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _env(tmpdir)
            env.update(
                {
                    "DB_HOST": "host",
                    "DB_PORT": str(port),
                    "DB_NAME": "db",
                    "DB_USER": "u",
                    "DB_PASSWORD": "p",
                }
            )
            env.pop("DATABASE_URL", None)
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert f":{port}/" in s.database_url

    @pytest.mark.parametrize("host", ["localhost", "db.example.com", "127.0.0.1"])
    def test_db_host_in_url(self, host):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _env(tmpdir)
            env.update(
                {
                    "DB_HOST": host,
                    "DB_NAME": "db",
                    "DB_USER": "u",
                    "DB_PASSWORD": "p",
                }
            )
            env.pop("DATABASE_URL", None)
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert host in s.database_url
