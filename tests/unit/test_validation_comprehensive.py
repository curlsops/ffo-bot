import pytest

from bot.utils.validation import InputValidator, ValidationError


class TestValidateDiscordIdComprehensive:
    @pytest.mark.parametrize("val", [0, 1, 100, 123456789012345678, 2**63, 2**64])
    def test_valid_ids(self, val):
        assert InputValidator.validate_discord_id(val, "id") == val
        assert InputValidator.validate_discord_id(str(val), "id") == val

    @pytest.mark.parametrize("val", [2**64 + 1, -1, -100])
    def test_out_of_range_raises(self, val):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(val, "id")

    @pytest.mark.parametrize("val", ["abc", "12.5", "", None, [], {}])
    def test_invalid_type_raises(self, val):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(val, "id")

    @pytest.mark.parametrize("field", ["user_id", "server_id", "channel_id"])
    def test_field_name_in_error(self, field):
        with pytest.raises(ValidationError) as exc:
            InputValidator.validate_discord_id("x", field)
        assert field in str(exc.value)


class TestValidateStringComprehensive:
    @pytest.mark.parametrize("s", ["a", "hello", "x" * 100])
    def test_valid_strings(self, s):
        result = InputValidator.validate_string(s, "f", max_length=200)
        assert result == s.strip()

    @pytest.mark.parametrize("max_len", [1, 5, 10, 50, 100, 500, 1000])
    def test_exactly_max_len(self, max_len):
        s = "a" * max_len
        assert InputValidator.validate_string(s, "f", max_length=max_len) == s

    @pytest.mark.parametrize("max_len", [1, 10, 100])
    def test_over_max_raises(self, max_len):
        with pytest.raises(ValidationError):
            InputValidator.validate_string("a" * (max_len + 1), "f", max_length=max_len)

    @pytest.mark.parametrize("val", [123, 0, True, None, [], {}])
    def test_non_string_raises(self, val):
        with pytest.raises(ValidationError):
            InputValidator.validate_string(val, "f", max_length=100)

    @pytest.mark.parametrize("s,max_len", [("a", 1), ("ab", 2), ("x" * 50, 50)])
    def test_at_boundary(self, s, max_len):
        assert InputValidator.validate_string(s, "f", max_length=max_len) == s


class TestValidateCommandNameComprehensive:
    @pytest.mark.parametrize(
        "name",
        [
            "a",
            "ab",
            "a1",
            "a_b",
            "test",
            "command_name",
            "x123",
            "my_command_123",
            "z" * 100,
        ],
    )
    def test_valid(self, name):
        assert InputValidator.validate_command_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "A",
            "a-b",
            "a b",
            "a!",
            "UPPER",
            "",
            "a.b",
            "a:b",
            "a b",
            "a\nb",
        ],
    )
    def test_invalid(self, name):
        with pytest.raises(ValidationError):
            InputValidator.validate_command_name(name)


class TestValidatePhrasePatternComprehensive:
    @pytest.mark.parametrize(
        "pattern",
        [
            r".",
            r"\d",
            r"\w+",
            r"^$",
            r"[a-z]",
            r"(a|b)",
            r"\s",
            r"\b",
        ],
    )
    def test_valid_patterns(self, pattern):
        assert InputValidator.validate_phrase_pattern(pattern) == pattern

    @pytest.mark.parametrize("pattern", [r"[", r"(?", r"*", r"(?P<>"])
    def test_invalid_patterns(self, pattern):
        with pytest.raises(ValidationError):
            InputValidator.validate_phrase_pattern(pattern)


class TestValidateEmojiComprehensive:
    @pytest.mark.parametrize("emoji", ["👋", "🎉", "😀", "👍", "🔥", "<:custom:123456789>"])
    def test_valid_emoji(self, emoji):
        assert InputValidator.validate_emoji(emoji) == emoji

    @pytest.mark.parametrize("val", ["", "   ", "x" * 256])
    def test_invalid_emoji(self, val):
        with pytest.raises(ValidationError):
            InputValidator.validate_emoji(val)


class TestSanitizeSqlComprehensive:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("a", "a"),
            ("", ""),
            ("hello", "hello"),
            ("a\x00", "a"),
            ("\x00a", "a"),
            ("a\x00b\x00c", "abc"),
        ],
    )
    def test_sanitize(self, inp, expected):
        assert InputValidator.sanitize_sql_parameter(inp) == expected
