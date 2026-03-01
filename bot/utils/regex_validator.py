import re
import time


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

    async def validate(self, pattern: str):
        if len(pattern) > self.MAX_PATTERN_LENGTH:
            raise RegexValidationError(
                f"Pattern exceeds maximum length of {self.MAX_PATTERN_LENGTH}"
            )

        for p in self.REDOS_PATTERNS:
            if p.search(pattern):
                raise RegexValidationError("Pattern contains potentially dangerous ReDoS construct")

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise RegexValidationError(f"Invalid regex: {e}")

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
                raise RegexValidationError(f"Pattern execution error: {e}")
            ms = (time.perf_counter() - start) * 1000
            if ms > self.MAX_EXECUTION_TIME_MS:
                raise RegexValidationError(
                    f"Pattern too slow ({ms:.2f}ms > {self.MAX_EXECUTION_TIME_MS}ms)"
                )
