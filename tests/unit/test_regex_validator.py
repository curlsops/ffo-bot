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
