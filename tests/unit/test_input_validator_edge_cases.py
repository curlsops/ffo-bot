import pytest

from bot.utils.validation import InputValidator, ValidationError


class TestValidateDiscordIdEdgeCases:
    @pytest.mark.parametrize("val", [0, 1, 2**63 - 1])
    def test_boundary_values(self, val):
        assert InputValidator.validate_discord_id(val, "id") == val

    @pytest.mark.parametrize("val", ["0", "1", "123456789"])
    def test_string_numbers(self, val):
        assert InputValidator.validate_discord_id(val, "id") == int(val)


class TestValidateStringEdgeCases:
    @pytest.mark.parametrize("max_len", [1, 10, 100, 2000])
    def test_max_length_boundaries(self, max_len):
        s = "a" * max_len
        assert InputValidator.validate_string(s, "x", max_length=max_len) == s

    @pytest.mark.parametrize("s", ["x", "ab", "hello", "a" * 50])
    def test_various_lengths(self, s):
        assert InputValidator.validate_string(s, "x", max_length=100) == s

    def test_unicode(self):
        s = "日本語"
        assert InputValidator.validate_string(s, "x", max_length=100) == s


class TestValidateCommandNameEdgeCases:
    @pytest.mark.parametrize(
        "name",
        ["a", "ab", "a1", "a_b", "test_123", "my_cmd", "x1", "cmd_2_test"],
    )
    def test_minimal_valid(self, name):
        assert InputValidator.validate_command_name(name) == name


class TestValidatePhrasePatternEdgeCases:
    def test_single_char_pattern(self):
        assert InputValidator.validate_phrase_pattern("a") == "a"

    def test_digit_pattern(self):
        assert InputValidator.validate_phrase_pattern(r"\d") == r"\d"


class TestSanitizeSqlParameterEdgeCases:
    def test_empty_string(self):
        assert InputValidator.sanitize_sql_parameter("") == ""

    def test_no_nulls(self):
        s = "hello world"
        assert InputValidator.sanitize_sql_parameter(s) == s
