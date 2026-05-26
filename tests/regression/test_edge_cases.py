import pytest

from bot.utils.quotebook_channel import get_quotebook_channel_id
from bot.utils.server_roles import get_server_role_ids
from bot.utils.validation import InputValidator, ValidationError
from bot.utils.whitelist_channel import get_whitelist_channel_id
from tests.helpers import db_pool_with_conn, mock_db_conn


class TestConfigEdgeCases:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("config_val", [{}, None, {"other": 1}, "string", 123])
    async def test_get_server_role_ids_handles_bad_config(self, config_val):
        pool = db_pool_with_conn(mock_db_conn(fetchrow={"config": config_val}))
        result = await get_server_role_ids(pool, 1)
        assert isinstance(result, dict)
        if not (config_val and isinstance(config_val, dict)):
            assert result == {}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("row", [None, {"config": None}, {"config": {}}])
    async def test_channel_getters_handle_missing(self, row):
        pool = db_pool_with_conn(mock_db_conn(fetchrow=row))
        assert await get_whitelist_channel_id(pool, 1) is None
        assert await get_quotebook_channel_id(pool, 1) is None


class TestValidationEdgeCases:
    @pytest.mark.parametrize("val", ["", "   ", "\t"])
    def test_validate_string_empty_rejected(self, val):
        with pytest.raises(ValidationError):
            InputValidator.validate_string(val, "f", max_length=10)

    @pytest.mark.parametrize("val", [None, 0, [], {}])
    def test_validate_string_non_string_rejected(self, val):
        with pytest.raises(ValidationError):
            InputValidator.validate_string(val, "f", max_length=10)

    def test_validate_discord_id_negative_rejected(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(-1, "id")

    def test_validate_discord_id_over_64bit_rejected(self):
        with pytest.raises(ValidationError):
            InputValidator.validate_discord_id(2**64 + 1, "id")
