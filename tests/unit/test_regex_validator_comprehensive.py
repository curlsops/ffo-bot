import pytest

from bot.utils.regex_validator import RegexValidationError, RegexValidator


class TestRegexValidatorParametrized:
    @pytest.mark.parametrize("pattern", [r".", r"\d", r"\w+", r"^$", r"[a-z]", r"hello"])
    @pytest.mark.asyncio
    async def test_valid_patterns(self, pattern):
        v = RegexValidator()
        await v.validate(pattern)

    @pytest.mark.parametrize("pattern", [r"[", r"(?", r"*", r"(?P<>"])
    @pytest.mark.asyncio
    async def test_invalid_syntax_raises(self, pattern):
        v = RegexValidator()
        with pytest.raises(RegexValidationError):
            await v.validate(pattern)

    @pytest.mark.parametrize("length", [501, 502, 600, 1000])
    @pytest.mark.asyncio
    async def test_over_max_length_raises(self, length):
        v = RegexValidator()
        with pytest.raises(RegexValidationError):
            await v.validate("a" * length)

    @pytest.mark.parametrize("length", [1, 100, 499, 500])
    @pytest.mark.asyncio
    async def test_at_or_under_max_length_ok(self, length):
        v = RegexValidator()
        await v.validate("a" * length)

    def test_constants(self):
        assert RegexValidator.MAX_PATTERN_LENGTH == 500
        assert RegexValidator.TEST_STRING_LENGTH == 100
        assert RegexValidator.MAX_EXECUTION_TIME_MS == 100

    def test_redos_patterns_count(self):
        assert len(RegexValidator.REDOS_PATTERNS) == 6


class TestRegexValidationError:
    def test_message_preserved(self):
        with pytest.raises(RegexValidationError) as exc:
            raise RegexValidationError("custom message")
        assert str(exc.value) == "custom message"
