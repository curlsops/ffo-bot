"""Input validation and sanitization."""

import re
from typing import Any


class ValidationError(Exception):
    pass


class InputValidator:
    MAX_PHRASE_LENGTH = 500
    MAX_COMMAND_NAME_LENGTH = 100
    MAX_NOTES_LENGTH = 1000
    MAX_STRING_LENGTH = 2000
    COMMAND_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")

    @staticmethod
    def validate_discord_id(value: Any, field_name: str) -> int:
        try:
            discord_id = int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{field_name} must be a valid integer")
        if discord_id < 0 or discord_id > 2**64:
            raise ValidationError(f"{field_name} is out of valid range")
        return discord_id

    @staticmethod
    def validate_string(
        value: Any, field_name: str, max_length: int, allow_empty: bool = False
    ) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string")
        value = value.strip()
        if not value and not allow_empty:
            raise ValidationError(f"{field_name} cannot be empty")
        if len(value) > max_length:
            raise ValidationError(f"{field_name} exceeds maximum length of {max_length}")
        return value

    @staticmethod
    def validate_command_name(value: str) -> str:
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
        value = InputValidator.validate_string(value, "phrase", InputValidator.MAX_PHRASE_LENGTH)
        try:
            re.compile(value, re.IGNORECASE)
        except re.error as e:
            raise ValidationError(f"Invalid regex pattern: {e}")
        return value

    @staticmethod
    def sanitize_sql_parameter(value: str) -> str:
        return value.replace("\x00", "")

    @staticmethod
    def validate_emoji(value: str) -> str:
        return InputValidator.validate_string(value, "emoji", 255)
