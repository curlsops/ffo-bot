"""Input validation and sanitization."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Input validation error."""

    pass


class InputValidator:
    """Comprehensive input validation and sanitization."""

    # Maximum lengths to prevent DoS
    MAX_PHRASE_LENGTH = 500
    MAX_COMMAND_NAME_LENGTH = 100
    MAX_NOTES_LENGTH = 1000
    MAX_STRING_LENGTH = 2000

    # Allowed characters for specific fields
    COMMAND_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")

    @staticmethod
    def validate_discord_id(value: Any, field_name: str) -> int:
        """
        Validate Discord ID (snowflake).

        Args:
            value: Value to validate
            field_name: Field name for error messages

        Returns:
            Validated Discord ID as integer

        Raises:
            ValidationError: If validation fails
        """
        try:
            discord_id = int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{field_name} must be a valid integer")

        # Discord IDs are 64-bit integers
        if discord_id < 0 or discord_id > 2**64:
            raise ValidationError(f"{field_name} is out of valid range")

        return discord_id

    @staticmethod
    def validate_string(
        value: Any, field_name: str, max_length: int, allow_empty: bool = False
    ) -> str:
        """
        Validate and sanitize string input.

        Args:
            value: Value to validate
            field_name: Field name for error messages
            max_length: Maximum allowed length
            allow_empty: Whether to allow empty strings

        Returns:
            Validated and trimmed string

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string")

        # Trim whitespace
        value = value.strip()

        if not value and not allow_empty:
            raise ValidationError(f"{field_name} cannot be empty")

        if len(value) > max_length:
            raise ValidationError(f"{field_name} exceeds maximum length of {max_length}")

        return value

    @staticmethod
    def validate_command_name(value: str) -> str:
        """
        Validate slash command name format.

        Args:
            value: Command name to validate

        Returns:
            Validated command name

        Raises:
            ValidationError: If validation fails
        """
        value = InputValidator.validate_string(
            value, "command_name", InputValidator.MAX_COMMAND_NAME_LENGTH
        )

        if not InputValidator.COMMAND_NAME_PATTERN.match(value):
            raise ValidationError(
                "Command name must contain only lowercase letters, numbers, and underscores"
            )

        return value

    @staticmethod
    def validate_phrase_pattern(value: str) -> str:
        """
        Validate regex phrase pattern.

        Args:
            value: Regex pattern to validate

        Returns:
            Validated pattern

        Raises:
            ValidationError: If validation fails
        """
        value = InputValidator.validate_string(value, "phrase", InputValidator.MAX_PHRASE_LENGTH)

        # Test regex compilation
        try:
            re.compile(value, re.IGNORECASE)
        except re.error as e:
            raise ValidationError(f"Invalid regex pattern: {e}")

        return value

    @staticmethod
    def sanitize_sql_parameter(value: str) -> str:
        """
        Sanitize string for SQL (used with parameterized queries).

        Args:
            value: String to sanitize

        Returns:
            Sanitized string

        Note:
            When using parameterized queries, sanitization is primarily
            about data validation, not SQL injection prevention.
            The database driver handles proper escaping.
        """
        # Remove null bytes that could truncate strings
        return value.replace("\x00", "")

    @staticmethod
    def validate_emoji(value: str) -> str:
        """
        Validate emoji string.

        Args:
            value: Emoji to validate

        Returns:
            Validated emoji

        Raises:
            ValidationError: If validation fails
        """
        value = InputValidator.validate_string(value, "emoji", 255)

        return value
