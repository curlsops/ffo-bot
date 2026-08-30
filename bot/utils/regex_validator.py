import re
import time
from typing import TYPE_CHECKING

from bot.utils.telemetry import trace_span

if TYPE_CHECKING:
    from bot.utils.metrics import BotMetrics


class RegexValidationError(Exception):
    pass


class RegexValidator:
    REDOS_PATTERNS = [
        re.compile(r"\([^)]*\)\+"),
        re.compile(r"\([^)]*\)\*"),
        re.compile(r"\([^)]*\)\{"),
        re.compile(r"\([^)]*\)\([^)]*\)\+"),
        re.compile(r"\([^)]*\+\)\+"),
        re.compile(r"\([^)]*\*\)\*"),
    ]
    MAX_PATTERN_LENGTH = 500
    TEST_STRING_LENGTH = 100
    MAX_EXECUTION_TIME_MS = 100

    def __init__(self, metrics: "BotMetrics | None" = None):
        self.metrics = metrics

    def _reject(self, message: str) -> RegexValidationError:
        if self.metrics:
            self.metrics.errors_total.labels(error_type="regex_rejected").inc()
        return RegexValidationError(message)

    async def validate(self, pattern: str):
        with trace_span(
            "regex.validate",
            attributes={
                "regex.pattern_length": len(pattern),
            },
        ):
            if len(pattern) > self.MAX_PATTERN_LENGTH:
                raise self._reject(f"Pattern exceeds maximum length of {self.MAX_PATTERN_LENGTH}")

            for p in self.REDOS_PATTERNS:
                if p.search(pattern):
                    raise self._reject("Pattern contains potentially dangerous ReDoS construct")

            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                raise self._reject(f"Invalid regex: {e}")

            test_strings = [
                "a" * self.TEST_STRING_LENGTH,
                "aaaaab" * 20,
                "x" * self.TEST_STRING_LENGTH,
                "a" * 48 + "b",
            ]
            for test_str in test_strings:
                start = time.perf_counter()
                try:
                    compiled.search(test_str)
                except Exception as e:
                    raise self._reject(f"Pattern execution error: {e}")
                ms = (time.perf_counter() - start) * 1000
                if ms > self.MAX_EXECUTION_TIME_MS:
                    raise self._reject(
                        f"Pattern too slow ({ms:.2f}ms > {self.MAX_EXECUTION_TIME_MS}ms)"
                    )
