import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from config.settings import Settings


def make_env(tmpdir, **overrides):
    base = {
        "DISCORD_BOT_TOKEN": "test_token",
        "DISCORD_PUBLIC_KEY": "test_key",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "MEDIA_STORAGE_PATH": tmpdir,
    }
    base.update(overrides)
    return base


class TestSettingsValidation:
    def test_settings_log_level_validation_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_LEVEL="DEBUG"), clear=True):
                assert Settings().log_level == "DEBUG"

    def test_settings_log_level_validation_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_LEVEL="debug"), clear=True):
                assert Settings().log_level == "DEBUG"

    def test_settings_log_level_validation_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_LEVEL="INVALID"), clear=True):
                with pytest.raises(ValidationError):
                    Settings()

    def test_settings_log_format_validation_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_FORMAT="json"), clear=True):
                assert Settings().log_format == "json"

    def test_settings_log_format_validation_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_FORMAT="TEXT"), clear=True):
                assert Settings().log_format == "text"

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
    def test_settings_default_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir), clear=True):
                settings = Settings()
                assert settings.environment == "production"
                assert settings.db_pool_min_size == 5
                assert settings.db_pool_max_size == 20
                assert settings.cache_max_size == 10000
                assert settings.cache_default_ttl == 86400
                assert settings.rate_limit_user_capacity == 10
                assert settings.rate_limit_server_capacity == 100
                assert settings.log_level == "INFO"
                assert settings.log_format == "json"
                assert settings.health_check_port == 8080
                assert settings.shutdown_timeout_seconds == 30
                assert settings.feature_media_download is True
                assert settings.feature_reaction_roles is True

    def test_settings_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MEDIA_STORAGE_PATH": tmpdir}, clear=True):
                with pytest.raises((ValidationError, ValueError)):
                    Settings()

    def test_settings_database_url_from_components(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "DISCORD_BOT_TOKEN": "t",
                "DISCORD_PUBLIC_KEY": "k",
                "MEDIA_STORAGE_PATH": tmpdir,
                "DB_HOST": "db.example.com",
                "DB_PORT": "5433",
                "DB_NAME": "mydb",
                "DB_USER": "myuser",
                "DB_PASSWORD": "secret",
            }
            with patch.dict(os.environ, env, clear=True):
                s = Settings()
                assert s.database_url == "postgresql://myuser:secret@db.example.com:5433/mydb"

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

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_settings_valid_log_levels(self, level):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_LEVEL=level), clear=True):
                assert Settings().log_level == level

    @pytest.mark.parametrize("fmt", ["json", "text"])
    def test_settings_valid_log_formats(self, fmt):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, make_env(tmpdir, LOG_FORMAT=fmt), clear=True):
                assert Settings().log_format == fmt
