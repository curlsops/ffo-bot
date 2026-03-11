import pytest

from config.constants import (
    AuditAction,
    Constants,
    FileType,
    Role,
)


class TestConstantsValues:
    @pytest.mark.parametrize(
        "attr,expected",
        [
            ("DISCORD_MESSAGE_LIMIT", 2000),
            ("REGEX_TIMEOUT_SECONDS", 0.5),
            ("MAX_PATTERN_LENGTH", 500),
            ("MAX_PHRASE_LENGTH", 500),
            ("MAX_COMMAND_NAME_LENGTH", 100),
            ("MAX_NOTES_LENGTH", 1000),
            ("MEDIA_CHUNK_SIZE", 8192),
            ("MEDIA_DOWNLOAD_TIMEOUT", 300),
            ("MESSAGE_RETENTION_DAYS", 365),
            ("AUDIT_LOG_RETENTION_DAYS", 730),
            ("CACHE_TTL", 86400),
            ("PERMISSION_CACHE_TTL", 86400),
            ("PHRASE_PATTERN_CACHE_TTL", 86400),
            ("USER_ROLE_CACHE_TTL", 86400),
            ("COMMAND_PERMISSION_CACHE_TTL", 86400),
        ],
    )
    def test_constant_value(self, attr, expected):
        assert getattr(Constants, attr) == expected


class TestRoleEnum:
    @pytest.mark.parametrize(
        "role,value",
        [
            (Role.SUPER_ADMIN, "super_admin"),
            (Role.ADMIN, "admin"),
            (Role.MODERATOR, "moderator"),
        ],
    )
    def test_role_value(self, role, value):
        assert role.value == value

    @pytest.mark.parametrize(
        "role,hierarchy",
        [
            (Role.SUPER_ADMIN, 3),
            (Role.ADMIN, 2),
            (Role.MODERATOR, 1),
        ],
    )
    def test_role_hierarchy(self, role, hierarchy):
        assert role.hierarchy == hierarchy

    def test_role_comparison(self):
        assert Role.SUPER_ADMIN.hierarchy > Role.ADMIN.hierarchy
        assert Role.ADMIN.hierarchy > Role.MODERATOR.hierarchy


class TestFileTypeEnum:
    @pytest.mark.parametrize(
        "ft,value",
        [
            (FileType.IMAGE, "image"),
            (FileType.VIDEO, "video"),
            (FileType.GIF, "gif"),
        ],
    )
    def test_file_type_value(self, ft, value):
        assert ft.value == value


class TestAuditActionEnum:
    @pytest.mark.parametrize(
        "action",
        [
            AuditAction.PERMISSION_GRANTED,
            AuditAction.PERMISSION_REVOKED,
            AuditAction.PERMISSION_DENIED,
            AuditAction.PHRASE_ADDED,
            AuditAction.PHRASE_REMOVED,
            AuditAction.ROLE_CONFIGURED,
            AuditAction.COMMAND_EXECUTED,
            AuditAction.CONFIG_CHANGED,
        ],
    )
    def test_audit_action_has_value(self, action):
        assert action.value
        assert isinstance(action.value, str)
