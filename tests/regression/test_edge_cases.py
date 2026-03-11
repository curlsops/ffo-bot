from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.quotebook_channel import get_quotebook_channel_id
from bot.utils.server_roles import get_server_role_ids
from bot.utils.validation import InputValidator, ValidationError
from bot.utils.whitelist_channel import get_whitelist_channel_id
from config.constants import Constants, Role


def _make_pool(fetchrow_result):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


class TestConfigEdgeCases:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("config_val", [{}, None, {"other": 1}, "string", 123])
    async def test_get_server_role_ids_handles_bad_config(self, config_val):
        result = await get_server_role_ids(_make_pool({"config": config_val}), 1)
        assert isinstance(result, dict)
        if not (config_val and isinstance(config_val, dict)):
            assert result == {}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("row", [None, {"config": None}, {"config": {}}])
    async def test_channel_getters_handle_missing(self, row):
        pool = _make_pool(row)
        whitelist_id = await get_whitelist_channel_id(pool, 1)
        quotebook_id = await get_quotebook_channel_id(pool, 1)
        assert whitelist_id is None or isinstance(whitelist_id, int)
        assert quotebook_id is None or isinstance(quotebook_id, int)


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


class TestConstantsRegression:
    def test_discord_limit_2000(self):
        assert Constants.DISCORD_MESSAGE_LIMIT == 2000

    def test_role_hierarchy_ordering(self):
        assert Role.SUPER_ADMIN.hierarchy > Role.ADMIN.hierarchy > Role.MODERATOR.hierarchy

    @pytest.mark.parametrize("attr", ["MAX_PHRASE_LENGTH", "MAX_COMMAND_NAME_LENGTH"])
    def test_length_limits_positive(self, attr):
        assert getattr(Constants, attr) > 0
