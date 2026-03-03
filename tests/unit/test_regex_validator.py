from unittest.mock import MagicMock, patch

import pytest

from bot.utils.regex_validator import RegexValidationError, RegexValidator


@pytest.mark.asyncio
async def test_valid_pattern():
    validator = RegexValidator()
    await validator.validate(r"hello")


@pytest.mark.parametrize(
    "pattern",
    [r"(a+)+", r"(a*)*", r"(a){1,10}", r"(a+)+$", r"^(.+)+$"],
)
@pytest.mark.asyncio
async def test_dangerous_pattern(pattern):
    validator = RegexValidator()
    with pytest.raises(RegexValidationError):
        await validator.validate(pattern)


@pytest.mark.asyncio
async def test_pattern_too_long():
    validator = RegexValidator()

    long_pattern = "a" * 600

    with pytest.raises(RegexValidationError):
        await validator.validate(long_pattern)


@pytest.mark.parametrize("pattern", [r"[abc", r"(unclosed", r"*invalid"])
@pytest.mark.asyncio
async def test_invalid_regex(pattern):
    validator = RegexValidator()
    with pytest.raises(RegexValidationError):
        await validator.validate(pattern)


@pytest.mark.asyncio
async def test_pattern_execution_error():
    validator = RegexValidator()

    await validator.validate(r"simple")


@pytest.mark.parametrize(
    "pattern",
    [r"hello\s+world", r"\d{3}-\d{4}", r"[a-zA-Z]+@[a-zA-Z]+\.[a-zA-Z]+", r"^test$", r"\w+"],
)
@pytest.mark.asyncio
async def test_valid_complex_pattern(pattern):
    validator = RegexValidator()
    await validator.validate(pattern)


@pytest.mark.asyncio
async def test_pattern_execution_exception():
    validator = RegexValidator()
    mock_pattern = MagicMock()
    mock_pattern.search.side_effect = Exception("Search failed")

    with patch("re.compile", return_value=mock_pattern):
        with pytest.raises(RegexValidationError) as exc_info:
            await validator.validate(r"test")

        assert "Pattern execution error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_pattern_slow_execution():
    validator = RegexValidator()
    call_count = [0]
    start_time = 1000.0

    def mock_perf_counter():
        call_count[0] += 1
        if call_count[0] % 2 == 1:
            return start_time
        else:
            return start_time + 0.2

    with patch("time.perf_counter", side_effect=mock_perf_counter):
        with pytest.raises(RegexValidationError) as exc_info:
            await validator.validate(r"simple")

        assert "too slow" in str(exc_info.value)
