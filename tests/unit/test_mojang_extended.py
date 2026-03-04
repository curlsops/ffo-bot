from unittest.mock import patch

import pytest

from bot.services.mojang import _format_uuid, get_profile, username_exists


class TestFormatUuid:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("a" * 32, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            ("0123456789abcdef0123456789abcdef", "01234567-89ab-cdef-0123-456789abcdef"),
        ],
    )
    def test_formats_32_char(self, raw, expected):
        assert _format_uuid(raw) == expected

    def test_preserves_36_char_uuid(self):
        u = "550e8400-e29b-41d4-a716-446655440000"
        assert _format_uuid(u) == u


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        with patch("bot.services.mojang._get_profile_from_mojang", return_value=None):
            with patch("bot.services.mojang._get_profile_from_namemc", return_value=None):
                result = await get_profile("nonexistent_user_xyz_12345")
                assert result is None

    @pytest.mark.asyncio
    async def test_mojang_success_returns_tuple(self):
        with patch(
            "bot.services.mojang._get_profile_from_mojang",
            return_value=("uuid-here", "Steve"),
        ):
            result = await get_profile("Steve")
            assert result == ("uuid-here", "Steve")


class TestUsernameExists:
    @pytest.mark.asyncio
    async def test_exists_when_profile_found(self):
        with patch(
            "bot.services.mojang._get_profile_from_mojang",
            return_value=("uuid", "name"),
        ):
            assert await username_exists("Steve") is True

    @pytest.mark.asyncio
    async def test_not_exists_when_no_profile(self):
        with patch("bot.services.mojang._get_profile_from_mojang", return_value=None):
            assert await username_exists("nonexistent") is False
