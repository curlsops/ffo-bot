"""Regex validation with ReDoS protection."""

import logging
import re
import time

logger = logging.getLogger(__name__)


class RegexValidationError(Exception):
    """Regex validation error."""

    pass


class RegexValidator:
    """Validate regex patterns to prevent ReDoS attacks."""

    # Patterns known to cause exponential backtracking
    REDOS_PATTERNS = [
        re.compile(r"\([^)]*\)\+"),  # (a+)+
        re.compile(r"\([^)]*\)\*"),  # (a*)*
        re.compile(r"\([^)]*\)\{"),  # (a){n,m}
        re.compile(r"\([^)]*\)\([^)]*\)\+"),  # (a)(b)+
        re.compile(r"\([^)]*\+\)\+"),  # (a+)+
        re.compile(r"\([^)]*\*\)\*"),  # (a*)*
    ]

    MAX_PATTERN_LENGTH = 500
    TEST_STRING_LENGTH = 100
    MAX_EXECUTION_TIME_MS = 100

    async def validate(self, pattern: str):
        """Validate regex pattern for ReDoS vulnerabilities."""
        if len(pattern) > self.MAX_PATTERN_LENGTH:
            raise RegexValidationError(
                f"Pattern exceeds maximum length of {self.MAX_PATTERN_LENGTH}"
            )

        # Check for known dangerous patterns
        for dangerous_pattern in self.REDOS_PATTERNS:
            if dangerous_pattern.search(pattern):
                raise RegexValidationError(
                    "Pattern contains potentially dangerous construct that could cause ReDoS"
                )

        # Test pattern performance
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise RegexValidationError(f"Invalid regex: {e}")

        # Test with worst-case strings (repeated characters)
        test_strings = [
            "a" * self.TEST_STRING_LENGTH,
            "aaaaab" * 20,
            "x" * self.TEST_STRING_LENGTH,
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab",  # Pathological case
        ]

        for test_str in test_strings:
            start_time = time.perf_counter()
            try:
                compiled.search(test_str)
            except Exception as e:
                raise RegexValidationError(f"Pattern execution error: {e}")

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            if execution_time_ms > self.MAX_EXECUTION_TIME_MS:
                logger.warning(f"Pattern '{pattern}' took {execution_time_ms:.2f}ms on test string")
                raise RegexValidationError(
                    f"Pattern execution time ({execution_time_ms:.2f}ms) exceeds "
                    f"safety threshold ({self.MAX_EXECUTION_TIME_MS}ms)"
                )

        logger.debug(f"Pattern '{pattern}' validated successfully")
