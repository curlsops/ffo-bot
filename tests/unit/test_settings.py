"""Tests for settings configuration."""

import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from config.settings import Settings


class TestSettingsValidation:
    """Tests for settings validation."""

    def test_settings_log_level_validation_valid(self):
        """Test valid log levels are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "LOG_LEVEL": "DEBUG",
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                settings = Settings()
                assert settings.log_level == "DEBUG"

    def test_settings_log_level_validation_case_insensitive(self):
        """Test log level validation is case insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "LOG_LEVEL": "debug",
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                settings = Settings()
                assert settings.log_level == "DEBUG"

    def test_settings_log_level_validation_invalid(self):
        """Test invalid log level raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "LOG_LEVEL": "INVALID",
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                with pytest.raises(ValidationError):
                    Settings()

    def test_settings_log_format_validation_valid(self):
        """Test valid log formats are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "LOG_FORMAT": "json",
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                settings = Settings()
                assert settings.log_format == "json"

    def test_settings_log_format_validation_text(self):
        """Test text log format is accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "LOG_FORMAT": "TEXT",
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                settings = Settings()
                assert settings.log_format == "text"

    def test_settings_log_format_validation_invalid(self):
        """Test invalid log format raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "LOG_FORMAT": "xml",
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                with pytest.raises(ValidationError):
                    Settings()

    def test_settings_media_storage_path_creates_directory(self):
        """Test media storage path creates directory if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_path = os.path.join(tmpdir, "new_media_folder")

            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "MEDIA_STORAGE_PATH": new_path,
            }, clear=True):
                settings = Settings()
                assert os.path.exists(new_path)


class TestSettingsDefaults:
    """Tests for settings defaults."""

    def test_settings_default_values(self):
        """Test default settings values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "test_token",
                "DISCORD_PUBLIC_KEY": "test_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                settings = Settings()

                assert settings.environment == "production"
                assert settings.db_pool_min_size == 5
                assert settings.db_pool_max_size == 20
                assert settings.cache_max_size == 10000
                assert settings.cache_default_ttl == 300
                assert settings.rate_limit_user_capacity == 10
                assert settings.rate_limit_server_capacity == 100
                assert settings.log_level == "INFO"
                assert settings.log_format == "json"
                assert settings.health_check_port == 8080
                assert settings.shutdown_timeout_seconds == 30
                assert settings.feature_media_download is True
                assert settings.feature_notifiarr_monitoring is True
                assert settings.feature_reaction_roles is True

    def test_settings_required_fields(self):
        """Test required fields are enforced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "MEDIA_STORAGE_PATH": tmpdir,
            }, clear=True):
                with pytest.raises(ValidationError):
                    Settings()
