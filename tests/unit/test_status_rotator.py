from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.tasks.status_rotator import StatusRotator


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.settings = MagicMock()
    bot.settings.feature_rotating_status = False
    bot.wait_until_ready = AsyncMock()
    bot.change_presence = AsyncMock()
    return bot


@pytest.fixture
def rotator(mock_bot):
    return StatusRotator(mock_bot)


class TestStatusRotatorInit:
    def test_init(self, mock_bot):
        r = StatusRotator(mock_bot)
        assert r.bot == mock_bot

    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.tasks.status_rotator import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()


class TestStatusRotatorCogLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_disabled(self, rotator):
        rotator.bot.settings.feature_rotating_status = False
        with patch.object(rotator.rotate_status, "start") as mock_start:
            await rotator.cog_load()
            mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_cog_load_enabled(self, rotator):
        rotator.bot.settings.feature_rotating_status = True
        with patch.object(rotator.rotate_status, "start") as mock_start:
            await rotator.cog_load()
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload(self, rotator):
        with patch.object(rotator.rotate_status, "cancel") as mock_cancel:
            await rotator.cog_unload()
            mock_cancel.assert_called_once()


class TestStatusRotatorFetchJoke:
    @pytest.mark.asyncio
    async def test_fetch_dad_joke_success(self, rotator):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={"joke": "Why did the scarecrow win an award? He was outstanding."}
        )

        with patch("aiohttp.ClientSession") as mock_session:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock()
            mock_ctx.get = MagicMock(return_value=AsyncCtx(mock_resp))
            mock_session.return_value = mock_ctx

            joke = await rotator._fetch_dad_joke()
            assert joke == "Why did the scarecrow win an award? He was outstanding."

    @pytest.mark.asyncio
    async def test_fetch_dad_joke_api_error(self, rotator):
        mock_resp = AsyncMock()
        mock_resp.status = 500

        with patch("aiohttp.ClientSession") as mock_session:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock()
            mock_ctx.get = MagicMock(return_value=AsyncCtx(mock_resp))
            mock_session.return_value = mock_ctx

            joke = await rotator._fetch_dad_joke()
            assert joke is None

    @pytest.mark.asyncio
    async def test_fetch_dad_joke_empty(self, rotator):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"joke": ""})

        with patch("aiohttp.ClientSession") as mock_session:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock()
            mock_ctx.get = MagicMock(return_value=AsyncCtx(mock_resp))
            mock_session.return_value = mock_ctx

            joke = await rotator._fetch_dad_joke()
            assert joke is None

    @pytest.mark.asyncio
    async def test_fetch_dad_joke_exception(self, rotator):
        with patch("aiohttp.ClientSession", side_effect=Exception("Network error")):
            joke = await rotator._fetch_dad_joke()
            assert joke is None


class TestStatusRotatorRotate:
    @pytest.mark.asyncio
    async def test_rotate_status_success(self, rotator):
        with patch.object(rotator, "_fetch_dad_joke", return_value="Test joke"):
            await rotator.rotate_status()
            rotator.bot.change_presence.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_status_no_joke(self, rotator):
        with patch.object(rotator, "_fetch_dad_joke", return_value=None):
            await rotator.rotate_status()
            rotator.bot.change_presence.assert_not_called()

    @pytest.mark.asyncio
    async def test_rotate_status_truncates_long_joke(self, rotator):
        long_joke = "A" * 200
        with patch.object(rotator, "_fetch_dad_joke", return_value=long_joke):
            await rotator.rotate_status()
            rotator.bot.change_presence.assert_called_once()
            activity = rotator.bot.change_presence.call_args[1]["activity"]
            assert len(activity.name) <= 128
            assert activity.name.endswith("...")

    @pytest.mark.asyncio
    async def test_rotate_status_handles_presence_error(self, rotator):
        rotator.bot.change_presence = AsyncMock(side_effect=Exception("Discord error"))
        with patch.object(rotator, "_fetch_dad_joke", return_value="Test joke"):
            await rotator.rotate_status()

    @pytest.mark.asyncio
    async def test_before_rotate(self, rotator):
        await rotator.before_rotate()
        rotator.bot.wait_until_ready.assert_called_once()


class AsyncCtx:
    def __init__(self, val):
        self.val = val

    async def __aenter__(self):
        return self.val

    async def __aexit__(self, *_):
        pass
