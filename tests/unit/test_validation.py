"""Test input validation."""

import pytest

from bot.utils.validation import InputValidator, ValidationError


def test_validate_discord_id_valid():
    """Test valid Discord ID."""
    result = InputValidator.validate_discord_id("123456789012345678", "user_id")
    assert result == 123456789012345678


def test_validate_discord_id_invalid():
    """Test invalid Discord ID."""
    with pytest.raises(ValidationError):
        InputValidator.validate_discord_id("not_a_number", "user_id")


def test_validate_string_max_length():
    """Test string max length validation."""
    with pytest.raises(ValidationError):
        InputValidator.validate_string("a" * 1000, "test", max_length=100)


def test_validate_command_name_valid():
    """Test valid command name."""
    result = InputValidator.validate_command_name("reactbot_phrases")
    assert result == "reactbot_phrases"


def test_validate_command_name_invalid_chars():
    """Test invalid command name with special characters."""
    with pytest.raises(ValidationError):
        InputValidator.validate_command_name("reactbot-phrases!")


def test_validate_emoji():
    """Test emoji validation."""
    result = InputValidator.validate_emoji("👋")
    assert result == "👋"


def test_validate_discord_id_out_of_range():
    """Test Discord ID out of valid range."""
    with pytest.raises(ValidationError):
        InputValidator.validate_discord_id(-1, "user_id")


def test_validate_string_not_string():
    """Test validate_string with non-string input."""
    with pytest.raises(ValidationError):
        InputValidator.validate_string(12345, "test", max_length=100)


def test_validate_string_empty_not_allowed():
    """Test validate_string rejects empty string when not allowed."""
    with pytest.raises(ValidationError):
        InputValidator.validate_string("   ", "test", max_length=100, allow_empty=False)


def test_validate_string_empty_allowed():
    """Test validate_string allows empty string when allowed."""
    result = InputValidator.validate_string("   ", "test", max_length=100, allow_empty=True)
    assert result == ""


def test_validate_phrase_pattern_valid():
    """Test validate_phrase_pattern with valid regex."""
    result = InputValidator.validate_phrase_pattern(r"hello\s+world")
    assert result == r"hello\s+world"


def test_validate_phrase_pattern_invalid():
    """Test validate_phrase_pattern with invalid regex."""
    with pytest.raises(ValidationError):
        InputValidator.validate_phrase_pattern(r"[invalid")


def test_sanitize_sql_parameter():
    """Test sanitize_sql_parameter removes null bytes."""
    result = InputValidator.sanitize_sql_parameter("hello\x00world")
    assert result == "helloworld"


def test_validate_emoji_empty():
    """Test validate_emoji rejects empty string."""
    with pytest.raises(ValidationError):
        InputValidator.validate_emoji("   ")


def test_validate_emoji_whitespace_only():
    """Test validate_emoji rejects whitespace-only string."""
    with pytest.raises(ValidationError) as exc_info:
        InputValidator.validate_emoji("   \t\n   ")

    assert "empty" in str(exc_info.value).lower()
