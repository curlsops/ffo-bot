from unittest.mock import MagicMock, patch

from bot.utils.discord_voice import (
    VOICE_DEPS_MISSING_USER_MSG,
    discord_voice_dependencies_available,
    log_voice_dependency_status,
)


def test_discord_voice_dependencies_available_true():
    with patch("importlib.util.find_spec", return_value=MagicMock()):
        assert discord_voice_dependencies_available() is True


def test_discord_voice_dependencies_available_false():
    with patch("importlib.util.find_spec", return_value=None):
        assert discord_voice_dependencies_available() is False


def test_voice_deps_missing_message_non_empty():
    assert "davey" in VOICE_DEPS_MISSING_USER_MSG.lower()


def test_log_voice_dependency_status_missing(caplog):
    import logging

    caplog.set_level(logging.WARNING)
    with patch(
        "bot.utils.discord_voice.discord_voice_dependencies_available",
        return_value=False,
    ):
        log_voice_dependency_status()
    assert "davey" in caplog.text.lower()


def test_log_voice_dependency_status_ok(caplog):
    import logging

    caplog.set_level(logging.INFO)
    with patch(
        "bot.utils.discord_voice.discord_voice_dependencies_available",
        return_value=True,
    ):
        log_voice_dependency_status()
    assert "voice deps ok" in caplog.text.lower()


def test_log_voice_dependency_status_ok_debug(caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    with patch(
        "bot.utils.discord_voice.discord_voice_dependencies_available",
        return_value=True,
    ):
        log_voice_dependency_status()
    assert "dependency check passed" in caplog.text.lower()


def test_log_voice_dependency_status_missing_debug(caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    with patch(
        "bot.utils.discord_voice.discord_voice_dependencies_available",
        return_value=False,
    ):
        log_voice_dependency_status()
    assert "not importable" in caplog.text.lower()


def test_log_voice_dependency_status_ok_unknown_version(caplog):
    import importlib.metadata
    import logging

    caplog.set_level(logging.INFO)
    with (
        patch(
            "bot.utils.discord_voice.discord_voice_dependencies_available",
            return_value=True,
        ),
        patch(
            "importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError("davey"),
        ),
    ):
        log_voice_dependency_status()
    assert "unknown" in caplog.text.lower()
