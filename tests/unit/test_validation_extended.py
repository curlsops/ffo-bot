import pytest

from bot.utils.validation import InputValidator, ValidationError


class TestValidateDiscordId:
    @pytest.mark.parametrize("val", [0, 1, 2**63 - 1])
    def test_boundary_values(self, val):
        result = InputValidator.validate_discord_id(str(val), "id")
        assert result == val

    def test_negative_raises(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(-1, "id")

    def test_over_64_raises(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(2**64 + 1, "id")

    def test_float_string_raises(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id("123.5", "id")


class TestValidateString:
    @pytest.mark.parametrize("max_len", [1, 10, 100, 1000])
    def test_exactly_max_length(self, max_len):
        s = "a" * max_len
        assert InputValidator.validate_string(s, "f", max_length=max_len) == s

    @pytest.mark.parametrize("max_len", [1, 10, 100])
    def test_one_over_max_raises(self, max_len):
        with pytest.raises(ValidationError):
            InputValidator.validate_string("a" * (max_len + 1), "f", max_length=max_len)

    def test_error_message_contains_field(self):
        with pytest.raises(ValidationError) as exc:
            InputValidator.validate_string(123, "my_field", max_length=10)
        assert "my_field" in str(exc.value)


class TestValidateCommandName:
    @pytest.mark.parametrize("name", ["a", "ab", "a1", "a_b", "test_command", "x123"])
    def test_valid_names(self, name):
        assert InputValidator.validate_command_name(name) == name

    @pytest.mark.parametrize("name", ["A", "a-b", "a b", "a!", "UPPER"])
    def test_invalid_names(self, name):
        with pytest.raises(ValidationError):
            InputValidator.validate_command_name(name)


class TestValidatePhrasePattern:
    def test_valid_complex_regex(self):
        pattern = r"\b(hello|world)\b"
        assert InputValidator.validate_phrase_pattern(pattern) == pattern

    def test_unbalanced_bracket_raises(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_phrase_pattern("a[b")

    def test_empty_raises(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_phrase_pattern("")


class TestValidateEmoji:
    @pytest.mark.parametrize("emoji", ["👍", "😀", "🎉", "🔥"])
    def test_unicode_emoji(self, emoji):
        assert InputValidator.validate_emoji(emoji) == emoji


class TestSanitizeSqlParameter:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("normal", "normal"),
            ("a\x00b", "ab"),
            ("\x00\x00", ""),
            ("\x00a\x00b\x00", "ab"),
        ],
    )
    def test_sanitize(self, inp, expected):
        assert InputValidator.sanitize_sql_parameter(inp) == expected
