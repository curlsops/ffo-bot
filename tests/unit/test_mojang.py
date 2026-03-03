"""Tests for Mojang API client with NameMC fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.mojang import (
    _format_uuid,
    _get_profile_from_mojang,
    _get_profile_from_namemc,
    get_profile,
    username_exists,
)


def make_response_mock(status: int, json_data=None, text_data=None):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {"id": "069a79f444e94726a5befca90e38aaf5", "name": "Steve"})
    resp.text = AsyncMock(return_value=text_data or "")
    return resp


class TestFormatUuid:
    def test_32_char_uuid_gets_dashes(self):
        assert _format_uuid("069a79f444e94726a5befca90e38aaf5") == "069a79f4-44e9-4726-a5be-fca90e38aaf5"

    def test_already_dashed_uuid(self):
        assert _format_uuid("069a79f4-44e9-4726-a5be-fca90e38aaf5") == "069a79f4-44e9-4726-a5be-fca90e38aaf5"

    def test_short_uuid_returned_as_is(self):
        assert _format_uuid("short") == "short"


class TestGetProfileFromMojang:
    @pytest.mark.asyncio
    async def test_200_success(self):
        resp = make_response_mock(200, {"id": "069a79f444e94726a5befca90e38aaf5", "name": "Steve"})
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("Steve")
            assert result == ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")

    @pytest.mark.asyncio
    async def test_404_returns_none(self):
        resp = make_response_mock(404)
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("NonexistentUser")
            assert result is None

    @pytest.mark.asyncio
    async def test_403_tries_fallback(self):
        resp1 = make_response_mock(403)
        resp2 = make_response_mock(200, {"id": "abc123def456789012345678901234ab", "name": "TestUser"})
        ctx1 = MagicMock(__aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock(return_value=None))
        ctx2 = MagicMock(__aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.side_effect = [ctx1, ctx2]
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("TestUser")
            assert result is not None
            assert mock_session.get.call_count == 2

    @pytest.mark.asyncio
    async def test_429_tries_fallback(self):
        resp1 = make_response_mock(429)
        resp2 = make_response_mock(200, {"id": "abc123def456789012345678901234ab", "name": "TestUser"})
        ctx1 = MagicMock(__aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock(return_value=None))
        ctx2 = MagicMock(__aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.side_effect = [ctx1, ctx2]
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("TestUser")
            assert result is not None

    @pytest.mark.asyncio
    async def test_500_returns_none(self):
        resp = make_response_mock(500)
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("TestUser")
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        import aiohttp

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.side_effect = aiohttp.ClientError("Connection failed")
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("TestUser")
            assert result is None

    @pytest.mark.asyncio
    async def test_200_no_uuid_returns_none(self):
        resp = make_response_mock(200, {"name": "OddUser"})
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("OddUser")
            assert result is None

    @pytest.mark.asyncio
    async def test_uses_uuid_key_when_id_missing(self):
        resp = make_response_mock(200, {"uuid": "069a79f444e94726a5befca90e38aaf5", "name": "Steve"})
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_mojang("Steve")
            assert result == ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")


class TestGetProfileFromNameMC:
    @pytest.mark.asyncio
    async def test_200_with_uuid_in_html(self):
        html = '<html><title>Steve | NameMC</title><div data-id="069a79f444e94726a5befca90e38aaf5"></div></html>'
        resp = make_response_mock(200, text_data=html)
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_namemc("Steve")
            assert result == ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")

    @pytest.mark.asyncio
    async def test_200_profile_not_found(self):
        html = '<html><title>Profile Not Found</title></html>'
        resp = make_response_mock(200, text_data=html)
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_namemc("NonexistentUser")
            assert result is None

    @pytest.mark.asyncio
    async def test_404_returns_none(self):
        resp = make_response_mock(404)
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_namemc("NonexistentUser")
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        import aiohttp

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.side_effect = aiohttp.ClientError("Connection failed")
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_namemc("TestUser")
            assert result is None

    @pytest.mark.asyncio
    async def test_200_no_uuid_but_title_returns_partial(self):
        html = '<html><title>Steve | NameMC</title><div>no uuid here</div></html>'
        resp = make_response_mock(200, text_data=html)
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_namemc("Steve")
            assert result == (None, "Steve")

    @pytest.mark.asyncio
    async def test_200_empty_page_returns_none(self):
        html = '<html><title>NameMC</title></html>'
        resp = make_response_mock(200, text_data=html)
        ctx = MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))

        with patch("bot.services.mojang.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _get_profile_from_namemc("TestUser")
            assert result is None


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_mojang_success_no_namemc_call(self):
        with patch("bot.services.mojang._get_profile_from_mojang", new_callable=AsyncMock) as mock_mojang:
            with patch("bot.services.mojang._get_profile_from_namemc", new_callable=AsyncMock) as mock_namemc:
                mock_mojang.return_value = ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")
                result = await get_profile("Steve")
                assert result == ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")
                mock_namemc.assert_not_called()

    @pytest.mark.asyncio
    async def test_mojang_fails_namemc_fallback(self):
        with patch("bot.services.mojang._get_profile_from_mojang", new_callable=AsyncMock) as mock_mojang:
            with patch("bot.services.mojang._get_profile_from_namemc", new_callable=AsyncMock) as mock_namemc:
                mock_mojang.return_value = None
                mock_namemc.return_value = ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")
                result = await get_profile("Steve")
                assert result == ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")

    @pytest.mark.asyncio
    async def test_both_fail_returns_none(self):
        with patch("bot.services.mojang._get_profile_from_mojang", new_callable=AsyncMock) as mock_mojang:
            with patch("bot.services.mojang._get_profile_from_namemc", new_callable=AsyncMock) as mock_namemc:
                mock_mojang.return_value = None
                mock_namemc.return_value = None
                result = await get_profile("NonexistentUser")
                assert result is None

    @pytest.mark.asyncio
    async def test_namemc_no_uuid_returns_none(self):
        with patch("bot.services.mojang._get_profile_from_mojang", new_callable=AsyncMock) as mock_mojang:
            with patch("bot.services.mojang._get_profile_from_namemc", new_callable=AsyncMock) as mock_namemc:
                mock_mojang.return_value = None
                mock_namemc.return_value = (None, "Steve")
                result = await get_profile("Steve")
                assert result is None


class TestUsernameExists:
    @pytest.mark.asyncio
    async def test_mojang_success(self):
        with patch("bot.services.mojang._get_profile_from_mojang", new_callable=AsyncMock) as mock_mojang:
            mock_mojang.return_value = ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")
            result = await username_exists("Steve")
            assert result is True

    @pytest.mark.asyncio
    async def test_mojang_fails_namemc_success(self):
        with patch("bot.services.mojang._get_profile_from_mojang", new_callable=AsyncMock) as mock_mojang:
            with patch("bot.services.mojang._get_profile_from_namemc", new_callable=AsyncMock) as mock_namemc:
                mock_mojang.return_value = None
                mock_namemc.return_value = (None, "Steve")
                result = await username_exists("Steve")
                assert result is True

    @pytest.mark.asyncio
    async def test_both_fail(self):
        with patch("bot.services.mojang._get_profile_from_mojang", new_callable=AsyncMock) as mock_mojang:
            with patch("bot.services.mojang._get_profile_from_namemc", new_callable=AsyncMock) as mock_namemc:
                mock_mojang.return_value = None
                mock_namemc.return_value = None
                result = await username_exists("NonexistentUser")
                assert result is False
