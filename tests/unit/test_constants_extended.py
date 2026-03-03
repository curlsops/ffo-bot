import pytest

from config.constants import AuditAction, Constants, FileType, Role


class TestRoleExtended:
    @pytest.mark.parametrize("role", [Role.SUPER_ADMIN, Role.ADMIN, Role.MODERATOR])
    def test_role_has_value(self, role):
        assert role.value
        assert isinstance(role.value, str)

    @pytest.mark.parametrize("role", [Role.SUPER_ADMIN, Role.ADMIN, Role.MODERATOR])
    def test_role_has_hierarchy(self, role):
        assert role.hierarchy >= 1


class TestFileTypeExtended:
    @pytest.mark.parametrize("ft", [FileType.IMAGE, FileType.VIDEO, FileType.GIF])
    def test_file_type_value(self, ft):
        assert ft.value in ("image", "video", "gif")


class TestAuditActionExtended:
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
    def test_audit_action_value(self, action):
        assert action.value


class TestConstantsExtended:
    @pytest.mark.parametrize("attr", ["MAX_PHRASE_LENGTH", "MAX_COMMAND_NAME_LENGTH", "MAX_NOTES_LENGTH"])
    def test_length_constants(self, attr):
        val = getattr(Constants, attr)
        assert val > 0
        assert isinstance(val, int)

    @pytest.mark.parametrize("attr", ["MEDIA_CHUNK_SIZE", "MEDIA_DOWNLOAD_TIMEOUT"])
    def test_media_constants(self, attr):
        val = getattr(Constants, attr)
        assert val > 0

    @pytest.mark.parametrize("attr", ["MESSAGE_RETENTION_DAYS", "AUDIT_LOG_RETENTION_DAYS"])
    def test_retention_constants(self, attr):
        val = getattr(Constants, attr)
        assert val > 0

    @pytest.mark.parametrize(
        "attr",
        [
            "PERMISSION_CACHE_TTL",
            "PHRASE_PATTERN_CACHE_TTL",
            "USER_ROLE_CACHE_TTL",
            "COMMAND_PERMISSION_CACHE_TTL",
        ],
    )
    def test_cache_ttl_constants(self, attr):
        val = getattr(Constants, attr)
        assert val > 0
        assert isinstance(val, (int, float))
