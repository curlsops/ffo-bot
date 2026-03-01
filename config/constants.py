from enum import Enum


class Constants:
    REGEX_TIMEOUT_SECONDS = 0.5
    MAX_PATTERN_LENGTH = 500

    MAX_PHRASE_LENGTH = 500
    MAX_COMMAND_NAME_LENGTH = 100
    MAX_NOTES_LENGTH = 1000

    MEDIA_CHUNK_SIZE = 8192
    MEDIA_DOWNLOAD_TIMEOUT = 300

    MESSAGE_RETENTION_DAYS = 365
    AUDIT_LOG_RETENTION_DAYS = 730

    PERMISSION_CACHE_TTL = 300
    PHRASE_PATTERN_CACHE_TTL = 300
    USER_ROLE_CACHE_TTL = 300
    COMMAND_PERMISSION_CACHE_TTL = 60


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"

    @property
    def hierarchy(self) -> int:
        hierarchy_map = {Role.SUPER_ADMIN: 3, Role.ADMIN: 2, Role.MODERATOR: 1}
        return hierarchy_map[self]


class FileType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"


class AuditAction(str, Enum):
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    PERMISSION_DENIED = "permission_denied"
    PHRASE_ADDED = "phrase_added"
    PHRASE_REMOVED = "phrase_removed"
    ROLE_CONFIGURED = "role_configured"
    COMMAND_EXECUTED = "command_executed"
    CONFIG_CHANGED = "config_changed"
