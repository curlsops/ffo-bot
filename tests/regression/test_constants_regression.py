import pytest

from config.constants import AuditAction, Constants, FileType, Role


class TestRoleRegression:
    @pytest.mark.parametrize("role", list(Role))
    def test_each_role_has_hierarchy(self, role):
        assert 1 <= role.hierarchy <= 3

    @pytest.mark.parametrize("role", list(Role))
    def test_role_value_snake_case(self, role):
        assert "_" in role.value or role.value.islower()


class TestConstantsRegression:
    def test_discord_limit(self):
        assert Constants.DISCORD_MESSAGE_LIMIT == 2000

    def test_regex_timeout_positive(self):
        assert Constants.REGEX_TIMEOUT_SECONDS > 0

    def test_media_timeout_positive(self):
        assert Constants.MEDIA_DOWNLOAD_TIMEOUT > 0

    def test_chunk_size_positive(self):
        assert Constants.MEDIA_CHUNK_SIZE > 0
