import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from config.settings import Settings


def make_env(tmpdir, **overrides):
    base = {
        "DISCORD_BOT_TOKEN": "t",
        "DISCORD_PUBLIC_KEY": "k",
        "DATABASE_URL": "postgresql://u:p@localhost/db",
        "MEDIA_STORAGE_PATH": tmpdir,
    }
    base.update(overrides)
    return base


class TestSettingsValidation:
    @pytest.mark.parametrize(
        "level,expected",
        [
            ("DEBUG", "DEBUG"),
            ("INFO", "INFO"),
            ("WARNING", "WARNING"),
            ("ERROR", "ERROR"),
            ("CRITICAL", "CRITICAL"),
            ("debug", "DEBUG"),
            ("info", "INFO"),
        ],
    )
    def test_settings_log_level_validation_valid(self, level, expected):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_LEVEL=level), clear=True):
                assert Settings().log_level == expected

    def test_settings_log_level_validation_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_LEVEL="INVALID"), clear=True):
                with pytest.raises(ValidationError):
                    Settings()

    @pytest.mark.parametrize(
        "fmt,expected",
        [("json", "json"), ("text", "text"), ("JSON", "json"), ("TEXT", "text")],
    )
    def test_settings_log_format_validation_valid(self, fmt, expected):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_FORMAT=fmt), clear=True):
                assert Settings().log_format == expected

    def test_settings_log_format_validation_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_FORMAT="xml"), clear=True):
                with pytest.raises(ValidationError):
                    Settings()

    def test_settings_media_storage_path_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_path = os.path.join(tmpdir, "new_media_folder")
            with patch.dict(os.environ, make_env(new_path), clear=True):
                Settings()
                assert os.path.exists(new_path)


class TestSettingsDefaults:
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
            ("log_level", "INFO"),
            ("log_format", "json"),
            ("health_check_port", 8080),
            ("health_check_host", "0.0.0.0"),
            ("shutdown_timeout_seconds", 30),
            ("sync_commands_on_boot", True),
            ("clear_commands_on_boot", True),
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
    def test_settings_default_values(self, field, expected):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir), clear=True):
                settings = Settings()
                assert getattr(settings, field) == expected

    def test_settings_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MEDIA_STORAGE_PATH": tmpdir}, clear=True):
                with pytest.raises((ValidationError, ValueError)):
                    Settings()

    @pytest.mark.parametrize("port", [5432, 5433, 3306])
    def test_settings_database_url_from_components(self, port):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "DISCORD_BOT_TOKEN": "t",
                "DISCORD_PUBLIC_KEY": "k",
                "MEDIA_STORAGE_PATH": tmpdir,
                "DB_HOST": "db.example.com",
                "DB_PORT": str(port),
                "DB_NAME": "mydb",
                "DB_USER": "myuser",
                "DB_PASSWORD": "secret",
            }
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert s.database_url == (f"postgresql://myuser:secret@db.example.com:{port}/mydb")

    @pytest.mark.parametrize("host", ["localhost", "db.example.com", "127.0.0.1"])
    def test_settings_database_url_from_components_host_variants(self, host):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "DISCORD_BOT_TOKEN": "t",
                "DISCORD_PUBLIC_KEY": "k",
                "MEDIA_STORAGE_PATH": tmpdir,
                "DB_HOST": host,
                "DB_NAME": "mydb",
                "DB_USER": "myuser",
                "DB_PASSWORD": "secret",
            }
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert host in s.database_url

    def test_settings_database_url_from_components_password_special_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "DISCORD_BOT_TOKEN": "t",
                "DISCORD_PUBLIC_KEY": "k",
                "MEDIA_STORAGE_PATH": tmpdir,
                "DB_HOST": "localhost",
                "DB_NAME": "test",
                "DB_USER": "u",
                "DB_PASSWORD": "p@ss:w/rd",
            }
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert "p%40ss%3Aw%2Frd" in s.database_url
                assert s.database_url.startswith("postgresql://u:")

    def test_settings_database_url_prefers_explicit_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "DISCORD_BOT_TOKEN": "t",
                "DISCORD_PUBLIC_KEY": "k",
                "MEDIA_STORAGE_PATH": tmpdir,
                "DATABASE_URL": "postgresql://explicit:url@host/db",
                "DB_HOST": "ignored",
                "DB_NAME": "ignored",
                "DB_USER": "ignored",
            }
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert s.database_url == "postgresql://explicit:url@host/db"

    def test_settings_database_url_incomplete_components_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "DISCORD_BOT_TOKEN": "t",
                "DISCORD_PUBLIC_KEY": "k",
                "MEDIA_STORAGE_PATH": tmpdir,
                "DB_HOST": "localhost",
                "DB_NAME": "test",
            }
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(ValueError, match="DATABASE_URL or all of"):
                    Settings()
