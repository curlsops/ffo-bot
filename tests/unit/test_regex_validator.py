from unittest.mock import MagicMock, patch

import pytest

from bot.utils.regex_validator import RegexValidationError, RegexValidator


@pytest.fixture
def validator():
    return RegexValidator()


async def assert_invalid_pattern(validator: RegexValidator, pattern: str) -> str:
    with pytest.raises(RegexValidationError) as exc_info:
        await validator.validate(pattern)
    return str(exc_info.value)


@pytest.mark.parametrize(
    "pattern",
    [
        r".",
        r"hello",
        r"\d",
        r"\d+",
        r"\w+",
        r"^$",
        r"^test$",
        r"\bword\b",
        r"[a-z]+",
        r"[0-9]+",
        r"test\d",
        r"x{1,5}",
        r"hello\s+world",
        r"\d{3}-\d{4}",
        r"[a-zA-Z]+@[a-zA-Z]+\.[a-zA-Z]+",
        "a" * 1,
        "a" * 100,
        "a" * 499,
        "a" * 500,
    ],
)
@pytest.mark.asyncio
async def test_validate_accepts_valid_patterns(validator, pattern):
    await validator.validate(pattern)


@pytest.mark.parametrize(
    "pattern",
    [r"[abc", r"[invalid", r"(unclosed", r"*invalid", r"*bad", r"?", r"[", r"(?", r"*", r"(?P<>"],
)
@pytest.mark.asyncio
async def test_validate_rejects_invalid_syntax(validator, pattern):
    message = await assert_invalid_pattern(validator, pattern)
    assert "Invalid regex" in message


@pytest.mark.parametrize("length", [501, 502, 600, 1000])
@pytest.mark.asyncio
async def test_validate_rejects_patterns_over_max_length(validator, length):
    message = await assert_invalid_pattern(validator, "a" * length)
    assert "exceeds maximum length" in message


@pytest.mark.parametrize(
    "pattern",
    [r"(a+)+", r"(a*)*", r"(a){1,10}", r"(a){1,}", r"(a+)+$", r"^(.+)+$"],
)
@pytest.mark.asyncio
async def test_validate_rejects_redos_patterns(validator, pattern):
    message = await assert_invalid_pattern(validator, pattern)
    assert "potentially dangerous ReDoS construct" in message


@pytest.mark.asyncio
async def test_validate_handles_pattern_execution_exception(validator):
    mock_pattern = MagicMock()
    mock_pattern.search.side_effect = Exception("Search failed")

    with patch("re.compile", return_value=mock_pattern):
        message = await assert_invalid_pattern(validator, r"test")
    assert "Pattern execution error" in message


@pytest.mark.asyncio
async def test_validate_rejects_slow_execution(validator):
    call_count = [0]
    start_time = 1000.0

    def mock_perf_counter():
        call_count[0] += 1
        if call_count[0] % 2 == 1:
            return start_time
        return start_time + 0.2

    with patch("time.perf_counter", side_effect=mock_perf_counter):
        message = await assert_invalid_pattern(validator, r"simple")
    assert "Pattern too slow" in message


def test_regex_validator_constants():
    assert RegexValidator.MAX_PATTERN_LENGTH == 500
    assert RegexValidator.TEST_STRING_LENGTH == 100
    assert RegexValidator.MAX_EXECUTION_TIME_MS == 100
    assert len(RegexValidator.REDOS_PATTERNS) == 6


def test_regex_validation_error_preserves_message():
    assert str(RegexValidationError("custom message")) == "custom message"
