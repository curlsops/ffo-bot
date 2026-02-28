import pytest

from bot.utils.validation import InputValidator, ValidationError


def test_validate_discord_id_valid():
    assert InputValidator.validate_discord_id("123456789012345678", "user_id") == 123456789012345678


def test_validate_discord_id_invalid():
    with pytest.raises(ValidationError):
        InputValidator.validate_discord_id("not_a_number", "user_id")


def test_validate_string_max_length():
    with pytest.raises(ValidationError):
        InputValidator.validate_string("a" * 1000, "test", max_length=100)


def test_validate_command_name_valid():
    assert InputValidator.validate_command_name("reactbot_phrases") == "reactbot_phrases"


def test_validate_command_name_invalid_chars():
    with pytest.raises(ValidationError):
        InputValidator.validate_command_name("reactbot-phrases!")


def test_validate_emoji():
    assert InputValidator.validate_emoji("👋") == "👋"


def test_validate_discord_id_out_of_range():
    with pytest.raises(ValidationError):
        InputValidator.validate_discord_id(-1, "user_id")


def test_validate_string_not_string():
    with pytest.raises(ValidationError):
        InputValidator.validate_string(12345, "test", max_length=100)


def test_validate_string_empty_not_allowed():
    with pytest.raises(ValidationError):
        InputValidator.validate_string("   ", "test", max_length=100, allow_empty=False)


def test_validate_string_empty_allowed():
    assert InputValidator.validate_string("   ", "test", max_length=100, allow_empty=True) == ""


def test_validate_phrase_pattern_valid():
    assert InputValidator.validate_phrase_pattern(r"hello\s+world") == r"hello\s+world"


def test_validate_phrase_pattern_invalid():
    with pytest.raises(ValidationError):
        InputValidator.validate_phrase_pattern(r"[invalid")


def test_sanitize_sql_parameter():
    assert InputValidator.sanitize_sql_parameter("hello\x00world") == "helloworld"


def test_validate_emoji_empty():
    with pytest.raises(ValidationError):
        InputValidator.validate_emoji("   ")
    with pytest.raises(ValidationError):
        InputValidator.validate_emoji("")
