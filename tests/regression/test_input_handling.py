
import pytest

from bot.utils.validation import InputValidator, ValidationError


class TestDiscordIdInput:
    @pytest.mark.parametrize("bad", ["abc", "12.5", "", "  ", "1e10"])
    def test_invalid_formats_rejected(self, bad):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(bad, "user_id")

    @pytest.mark.parametrize("good", ["0", "123456789", str(2**63)])
    def test_valid_formats_accepted(self, good):
        result = InputValidator.validate_discord_id(good, "user_id")
        assert isinstance(result, int)
        assert result >= 0


class TestStringInput:
    def test_whitespace_stripped(self):
        assert InputValidator.validate_string("  x  ", "f", max_length=10) == "x"

    def test_allow_empty_with_whitespace(self):
        assert InputValidator.validate_string("   ", "f", max_length=10, allow_empty=True) == ""

    def test_exceeds_max_raises(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_string("x" * 11, "f", max_length=10)


class TestCommandNameInput:
    @pytest.mark.parametrize("bad", ["", "UPPER", "has-dash", "has space", "!"])
    def test_invalid_command_names(self, bad):
        with pytest.raises(ValidationError):
            InputValidator.validate_command_name(bad)


class TestPhrasePatternInput:
    def test_empty_pattern_rejected(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_phrase_pattern("")

    def test_invalid_regex_rejected(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_phrase_pattern("[unclosed")


class TestSqlSanitize:
    def test_null_bytes_removed(self):
        assert InputValidator.sanitize_sql_parameter("a\x00b\x00c") == "abc"

    def test_normal_string_unchanged(self):
        assert InputValidator.sanitize_sql_parameter("normal") == "normal"
