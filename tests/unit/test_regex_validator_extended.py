import pytest

from bot.utils.regex_validator import RegexValidationError, RegexValidator


class TestRegexValidator:
    @pytest.mark.parametrize(
        "pattern",
        [
            r"hello",
            r"\d+",
            r"[a-z]+",
            r"^test$",
            r"\bword\b",
            r"x{1,5}",
            r"[0-9]+",
            r"test\d",
        ],
    )
    @pytest.mark.asyncio
    async def test_valid_patterns(self, pattern):
        v = RegexValidator()
        await v.validate(pattern)

    @pytest.mark.parametrize("pattern", [r"[invalid", r"(unclosed", r"*bad", r"?"])
    @pytest.mark.asyncio
    async def test_invalid_patterns_raise(self, pattern):
        v = RegexValidator()
        with pytest.raises(RegexValidationError):
            await v.validate(pattern)

    @pytest.mark.parametrize(
        "pattern",
        [r"(a+)+", r"(a*)*", r"(a){1,}", r"(a+)+$", r"^(.+)+$"],
    )
    @pytest.mark.asyncio
    async def test_redos_patterns_rejected(self, pattern):
        v = RegexValidator()
        with pytest.raises(RegexValidationError):
            await v.validate(pattern)

    @pytest.mark.asyncio
    async def test_pattern_501_chars_rejected(self):
        v = RegexValidator()
        with pytest.raises(RegexValidationError):
            await v.validate("a" * 501)

    @pytest.mark.asyncio
    async def test_pattern_500_chars_accepted(self):
        v = RegexValidator()
        await v.validate("a" * 500)
