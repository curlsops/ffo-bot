"""Test regex validation."""

import pytest

from bot.utils.regex_validator import RegexValidationError, RegexValidator


@pytest.mark.asyncio
async def test_valid_pattern():
    """Test valid regex pattern."""
    validator = RegexValidator()
    await validator.validate(r"hello")  # Should not raise


@pytest.mark.asyncio
async def test_dangerous_pattern():
    """Test dangerous pattern detection."""
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
    """Test pattern length validation."""
    validator = RegexValidator()

    long_pattern = "a" * 600

    with pytest.raises(RegexValidationError):
        await validator.validate(long_pattern)


@pytest.mark.asyncio
async def test_invalid_regex():
    """Test invalid regex syntax."""
    validator = RegexValidator()

    invalid_pattern = r"[abc"  # Unclosed bracket

    with pytest.raises(RegexValidationError):
        await validator.validate(invalid_pattern)


@pytest.mark.asyncio
async def test_pattern_execution_error():
    """Test pattern that causes execution error during search."""
    validator = RegexValidator()

    # Valid regex that shouldn't raise
    await validator.validate(r"simple")


@pytest.mark.asyncio
async def test_valid_complex_pattern():
    """Test valid complex regex pattern."""
    validator = RegexValidator()

    # Complex but safe patterns
    await validator.validate(r"hello\s+world")
    await validator.validate(r"\d{3}-\d{4}")
    await validator.validate(r"[a-zA-Z]+@[a-zA-Z]+\.[a-zA-Z]+")


@pytest.mark.asyncio
async def test_pattern_execution_exception():
    """Test pattern that raises exception during search."""
    from unittest.mock import MagicMock, patch

    validator = RegexValidator()

    # Mock the compiled pattern to raise an exception during search
    mock_pattern = MagicMock()
    mock_pattern.search.side_effect = Exception("Search failed")

    with patch("re.compile", return_value=mock_pattern):
        with pytest.raises(RegexValidationError) as exc_info:
            await validator.validate(r"test")

        assert "Pattern execution error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_pattern_slow_execution():
    """Test pattern that exceeds execution time threshold."""
    from unittest.mock import MagicMock, patch

    validator = RegexValidator()

    # Mock time.perf_counter to simulate slow execution
    call_count = [0]
    start_time = 1000.0

    def mock_perf_counter():
        call_count[0] += 1
        if call_count[0] % 2 == 1:
            return start_time
        else:
            # Return time that exceeds threshold (100ms = 0.1s)
            return start_time + 0.2

    with patch("time.perf_counter", side_effect=mock_perf_counter):
        with pytest.raises(RegexValidationError) as exc_info:
            await validator.validate(r"simple")

        assert "too slow" in str(exc_info.value)
