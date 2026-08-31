import pytest

from bot.utils.validation import InputValidator, ValidationError


def assert_raises_validation_error(callback, *args, **kwargs) -> str:
    with pytest.raises(ValidationError) as exc_info:
        callback(*args, **kwargs)
    return str(exc_info.value)


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0),
        (1, 1),
        (2**63 - 1, 2**63 - 1),
        (2**63, 2**63),
        (2**64, 2**64),
        ("0", 0),
        ("1", 1),
        ("123456789012345678", 123456789012345678),
    ],
)
def test_validate_discord_id_valid(value, expected):
    assert InputValidator.validate_discord_id(value, "id") == expected


@pytest.mark.parametrize("value", [-1, -100, 2**64 + 1, str(2**64 + 1)])
def test_validate_discord_id_out_of_range(value):
    assert "out of valid range" in assert_raises_validation_error(
        InputValidator.validate_discord_id,
        value,
        "id",
    )


@pytest.mark.parametrize("value", ["abc", "123.5", "12.5", "", None, [], {}])
def test_validate_discord_id_invalid_integer(value):
    assert "must be a valid integer" in assert_raises_validation_error(
        InputValidator.validate_discord_id,
        value,
        "id",
    )


@pytest.mark.parametrize("field_name", ["user_id", "server_id", "channel_id", "my_field"])
def test_validate_discord_id_includes_field_name(field_name):
    message = assert_raises_validation_error(
        InputValidator.validate_discord_id,
        "not_number",
        field_name,
    )
    assert field_name in message


@pytest.mark.parametrize(
    "value,max_length,expected",
    [
        ("a", 1, "a"),
        ("ab", 2, "ab"),
        ("hello", 100, "hello"),
        ("x" * 50, 100, "x" * 50),
        ("a" * 1000, 1000, "a" * 1000),
        ("a" * 2000, 2000, "a" * 2000),
        ("日本語", 100, "日本語"),
        ("  foo  ", 100, "foo"),
    ],
)
def test_validate_string_valid(value, max_length, expected):
    assert InputValidator.validate_string(value, "field", max_length=max_length) == expected


@pytest.mark.parametrize("max_length", [1, 5, 10, 50, 100, 500, 1000])
def test_validate_string_accepts_exact_boundary(max_length):
    value = "a" * max_length
    assert InputValidator.validate_string(value, "field", max_length=max_length) == value


@pytest.mark.parametrize("max_length", [1, 10, 100])
def test_validate_string_rejects_over_max(max_length):
    message = assert_raises_validation_error(
        InputValidator.validate_string,
        "a" * (max_length + 1),
        "field",
        max_length=max_length,
    )
    assert "exceeds maximum length" in message


@pytest.mark.parametrize("value", [12345, 0, True, None, [], {}])
def test_validate_string_rejects_non_string(value):
    assert "my_field must be a string" in assert_raises_validation_error(
        InputValidator.validate_string,
        value,
        "my_field",
        max_length=10,
    )


def test_validate_string_rejects_empty_when_not_allowed():
    assert "cannot be empty" in assert_raises_validation_error(
        InputValidator.validate_string,
        "   ",
        "field",
        max_length=100,
        allow_empty=False,
    )


def test_validate_string_allows_empty_when_configured():
    assert InputValidator.validate_string("   ", "field", max_length=100, allow_empty=True) == ""


@pytest.mark.parametrize(
    "value",
    [
        "a",
        "ab",
        "a1",
        "a_b",
        "reactbot_phrases",
        "my_command",
        "test123",
        "command_name",
        "my_command_123",
        "z" * 100,
    ],
)
def test_validate_command_name_valid(value):
    assert InputValidator.validate_command_name(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "A",
        "UPPER",
        "UPPERCASE",
        "a-b",
        "a b",
        "with space",
        "a!",
        "a.b",
        "a:b",
        "a\nb",
    ],
)
def test_validate_command_name_invalid(value):
    assert_raises_validation_error(InputValidator.validate_command_name, value)


@pytest.mark.parametrize(
    "pattern",
    [
        ".",
        "a",
        r"\d",
        r"\w+",
        r"\s",
        r"\b",
        r"^$",
        r"^test$",
        r"[a-z]",
        r"(a|b)",
        r"\b(hello|world)\b",
        r"hello\s+world",
        r"\d{3}-\d{4}",
        r"[a-zA-Z]+@[a-zA-Z]+\.[a-zA-Z]+",
    ],
)
def test_validate_phrase_pattern_valid(pattern):
    assert InputValidator.validate_phrase_pattern(pattern) == pattern


@pytest.mark.parametrize("pattern", [r"[invalid", r"[", r"(?", r"*", r"(?P<>", "", "a" * 1000])
def test_validate_phrase_pattern_invalid(pattern):
    assert_raises_validation_error(InputValidator.validate_phrase_pattern, pattern)


@pytest.mark.parametrize("value", ["👋", "🎉", "😀", "👍", "🔥", "<:custom:123456789>"])
def test_validate_emoji_valid(value):
    assert InputValidator.validate_emoji(value) == value


@pytest.mark.parametrize("value", ["", "   ", "x" * 256])
def test_validate_emoji_invalid(value):
    assert_raises_validation_error(InputValidator.validate_emoji, value)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("a", "a"),
        ("", ""),
        ("hello", "hello"),
        ("hello\x00world", "helloworld"),
        ("test\x00value\x00", "testvalue"),
        ("\x00\x00\x00", ""),
        ("a\x00b", "ab"),
        ("\x00a\x00b\x00", "ab"),
        ("a\x00b\x00c", "abc"),
    ],
)
def test_sanitize_sql_parameter(value, expected):
    assert InputValidator.sanitize_sql_parameter(value) == expected
