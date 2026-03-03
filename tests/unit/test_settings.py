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
                assert settings.cache_default_ttl == 300
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
                with pytest.raises(ValidationError):
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
