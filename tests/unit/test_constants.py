from config.constants import AuditAction, Constants, FileType, Role


class TestRole:
    def test_role_values(self):
        assert Role.SUPER_ADMIN.value == "super_admin"
        assert Role.ADMIN.value == "admin"
        assert Role.MODERATOR.value == "moderator"

    def test_role_hierarchy(self):
        assert Role.SUPER_ADMIN.hierarchy == 3
        assert Role.ADMIN.hierarchy == 2
        assert Role.MODERATOR.hierarchy == 1

    def test_role_hierarchy_ordering(self):
        assert Role.SUPER_ADMIN.hierarchy > Role.ADMIN.hierarchy
        assert Role.ADMIN.hierarchy > Role.MODERATOR.hierarchy


class TestFileType:
    def test_file_type_values(self):
        assert FileType.IMAGE.value == "image"
        assert FileType.VIDEO.value == "video"
        assert FileType.GIF.value == "gif"


class TestAuditAction:
    def test_audit_action_values(self):
        assert AuditAction.PERMISSION_GRANTED.value == "permission_granted"
        assert AuditAction.PERMISSION_REVOKED.value == "permission_revoked"
        assert AuditAction.PERMISSION_DENIED.value == "permission_denied"
        assert AuditAction.PHRASE_ADDED.value == "phrase_added"
        assert AuditAction.PHRASE_REMOVED.value == "phrase_removed"
        assert AuditAction.ROLE_CONFIGURED.value == "role_configured"
        assert AuditAction.COMMAND_EXECUTED.value == "command_executed"
        assert AuditAction.CONFIG_CHANGED.value == "config_changed"


class TestConstants:
    def test_regex_constants(self):
        assert Constants.REGEX_TIMEOUT_SECONDS == 0.5
        assert Constants.MAX_PATTERN_LENGTH == 500

    def test_input_validation_constants(self):
        assert Constants.MAX_PHRASE_LENGTH == 500
        assert Constants.MAX_COMMAND_NAME_LENGTH == 100
        assert Constants.MAX_NOTES_LENGTH == 1000

    def test_media_download_constants(self):
        assert Constants.MEDIA_CHUNK_SIZE == 8192
        assert Constants.MEDIA_DOWNLOAD_TIMEOUT == 300

    def test_database_retention_constants(self):
        assert Constants.MESSAGE_RETENTION_DAYS == 365
        assert Constants.AUDIT_LOG_RETENTION_DAYS == 730

    def test_cache_ttl_constants(self):
        assert Constants.PERMISSION_CACHE_TTL == 300
        assert Constants.PHRASE_PATTERN_CACHE_TTL == 300
        assert Constants.USER_ROLE_CACHE_TTL == 300
        assert Constants.COMMAND_PERMISSION_CACHE_TTL == 60
