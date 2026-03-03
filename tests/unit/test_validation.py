import pytest

from bot.utils.validation import InputValidator, ValidationError


class TestValidateDiscordId:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("123456789012345678", 123456789012345678),
            (0, 0),
            (str(2**63 - 1), 2**63 - 1),
        ],
    )
    def test_valid(self, inp, expected):
        assert InputValidator.validate_discord_id(inp, "user_id") == expected

    @pytest.mark.parametrize(
        "inp",
        ["not_a_number", -1, 2**64 + 1, str(2**64 + 1), None, [], {}],
    )
    def test_invalid(self, inp):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(inp, "user_id")


class TestValidateString:
    def test_valid(self):
        assert InputValidator.validate_string("test", "field", max_length=100) == "test"

    def test_exactly_max_length(self):
        assert len(InputValidator.validate_string("a" * 100, "field", max_length=100)) == 100

    def test_exceeds_max_length(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_string("a" * 1000, "field", max_length=100)

    def test_not_string(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_string(12345, "field", max_length=100)

    def test_empty_not_allowed(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_string("   ", "field", max_length=100, allow_empty=False)

    def test_empty_allowed(self):
        assert (
            InputValidator.validate_string("   ", "field", max_length=100, allow_empty=True) == ""
        )

    @pytest.mark.parametrize("inp", ["a", "x" * 50, "normal text"])
    def test_valid_various_lengths(self, inp):
        assert InputValidator.validate_string(inp, "field", max_length=100) == inp

    def test_strips_whitespace(self):
        assert InputValidator.validate_string("  foo  ", "field", max_length=100) == "foo"


class TestValidateCommandName:
    @pytest.mark.parametrize("inp", ["reactbot_phrases", "my_command", "test123"])
    def test_valid(self, inp):
        assert InputValidator.validate_command_name(inp) == inp

    @pytest.mark.parametrize("inp", ["reactbot-phrases!", "", "UPPERCASE", "with space"])
    def test_invalid(self, inp):
        with pytest.raises(ValidationError):
            InputValidator.validate_command_name(inp)


class TestValidatePhrasePattern:
    @pytest.mark.parametrize(
        "inp", [r"hello\s+world", r"\d{3}-\d{4}", r"[a-zA-Z]+@[a-zA-Z]+\.[a-zA-Z]+"]
    )
    def test_valid(self, inp):
        assert InputValidator.validate_phrase_pattern(inp) == inp

    @pytest.mark.parametrize(
        "inp,desc",
        [
            (r"[invalid", "bad_syntax"),
            ("", "empty"),
        ],
        ids=["bad_syntax", "empty"],
    )
    def test_invalid(self, inp, desc):
        with pytest.raises(ValidationError):
            InputValidator.validate_phrase_pattern(inp)

    def test_too_long(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_phrase_pattern("a" * 1000)


class TestValidateEmoji:
    @pytest.mark.parametrize("inp", ["👋", "🎉", "<:custom:123456789>"])
    def test_valid(self, inp):
        assert InputValidator.validate_emoji(inp) == inp

    @pytest.mark.parametrize("inp", ["   ", ""])
    def test_invalid(self, inp):
        with pytest.raises(ValidationError):
            InputValidator.validate_emoji(inp)

    @pytest.mark.parametrize("inp", ["😀", "👍", "🔥"])
    def test_valid_unicode_emoji(self, inp):
        assert InputValidator.validate_emoji(inp) == inp


class TestSanitizeSqlParameter:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("hello\x00world", "helloworld"),
            ("test\x00value\x00", "testvalue"),
            ("no_null", "no_null"),
            ("", ""),
            ("\x00\x00\x00", ""),
        ],
    )
    def test_removes_null_bytes(self, inp, expected):
        assert InputValidator.sanitize_sql_parameter(inp) == expected
