import pytest

from config.constants import AuditAction, Constants, Role


class TestRole:
    @pytest.mark.parametrize(
        "role,value,hierarchy",
        [
            (Role.SUPER_ADMIN, "super_admin", 3),
            (Role.ADMIN, "admin", 2),
            (Role.MODERATOR, "moderator", 1),
        ],
    )
    def test_role_values_and_hierarchy(self, role, value, hierarchy):
        assert role.value == value
        assert role.hierarchy == hierarchy
        assert isinstance(role.value, str)
        assert role.hierarchy >= 1

    def test_role_hierarchy_ordering(self):
        assert Role.SUPER_ADMIN.hierarchy > Role.ADMIN.hierarchy
        assert Role.ADMIN.hierarchy > Role.MODERATOR.hierarchy


class TestAuditAction:
    @pytest.mark.parametrize(
        "action,expected",
        [
            (AuditAction.PERMISSION_GRANTED, "permission_granted"),
            (AuditAction.PERMISSION_REVOKED, "permission_revoked"),
            (AuditAction.PERMISSION_DENIED, "permission_denied"),
            (AuditAction.PHRASE_ADDED, "phrase_added"),
            (AuditAction.PHRASE_REMOVED, "phrase_removed"),
            (AuditAction.ROLE_CONFIGURED, "role_configured"),
            (AuditAction.COMMAND_EXECUTED, "command_executed"),
            (AuditAction.CONFIG_CHANGED, "config_changed"),
        ],
    )
    def test_audit_action_values(self, action, expected):
        assert action.value == expected
        assert isinstance(action.value, str)
        assert action.value


class TestConstants:
    @pytest.mark.parametrize(
        "attr,expected",
        [
            ("DISCORD_MESSAGE_LIMIT", 2000),
            ("REGEX_TIMEOUT_SECONDS", 0.5),
            ("MAX_PATTERN_LENGTH", 500),
            ("MAX_PHRASE_LENGTH", 500),
            ("MAX_COMMAND_NAME_LENGTH", 100),
            ("MAX_NOTES_LENGTH", 1000),
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

    @pytest.mark.parametrize(
        "attr,expected_type",
        [
            ("MAX_PHRASE_LENGTH", int),
            ("MAX_COMMAND_NAME_LENGTH", int),
            ("MAX_NOTES_LENGTH", int),
            ("CACHE_TTL", (int, float)),
            ("PERMISSION_CACHE_TTL", (int, float)),
            ("PHRASE_PATTERN_CACHE_TTL", (int, float)),
            ("USER_ROLE_CACHE_TTL", (int, float)),
            ("COMMAND_PERMISSION_CACHE_TTL", (int, float)),
        ],
    )
    def test_numeric_constants_have_expected_type(self, attr, expected_type):
        assert isinstance(getattr(Constants, attr), expected_type)

    @pytest.mark.parametrize(
        "attr",
        [
            "REGEX_TIMEOUT_SECONDS",
            "MAX_PATTERN_LENGTH",
            "MESSAGE_RETENTION_DAYS",
            "AUDIT_LOG_RETENTION_DAYS",
            "CACHE_TTL",
            "PERMISSION_CACHE_TTL",
            "PHRASE_PATTERN_CACHE_TTL",
            "USER_ROLE_CACHE_TTL",
            "COMMAND_PERMISSION_CACHE_TTL",
        ],
    )
    def test_constants_are_positive(self, attr):
        assert getattr(Constants, attr) > 0
