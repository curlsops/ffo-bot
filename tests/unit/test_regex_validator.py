from unittest.mock import MagicMock, patch

import pytest

from bot.utils.regex_validator import RegexValidationError, RegexValidator


@pytest.mark.asyncio
async def test_valid_pattern():
    validator = RegexValidator()
    await validator.validate(r"hello")


@pytest.mark.asyncio
async def test_dangerous_pattern():
    validator = RegexValidator()

    dangerous_patterns = [
        r"(a+)+",
        r"(a*)*",
        r"(a){1,10}",
    ]

    for pattern in dangerous_patterns:
        with pytest.raises(RegexValidationError):
            await validator.validate(pattern)


@pytest.mark.asyncio
async def test_pattern_too_long():
    validator = RegexValidator()

    long_pattern = "a" * 600

    with pytest.raises(RegexValidationError):
        await validator.validate(long_pattern)


@pytest.mark.asyncio
async def test_invalid_regex():
    validator = RegexValidator()

    invalid_pattern = r"[abc"

    with pytest.raises(RegexValidationError):
        await validator.validate(invalid_pattern)


@pytest.mark.asyncio
async def test_pattern_execution_error():
    validator = RegexValidator()

    await validator.validate(r"simple")


@pytest.mark.asyncio
async def test_valid_complex_pattern():
    validator = RegexValidator()

    await validator.validate(r"hello\s+world")
    await validator.validate(r"\d{3}-\d{4}")
    await validator.validate(r"[a-zA-Z]+@[a-zA-Z]+\.[a-zA-Z]+")


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
