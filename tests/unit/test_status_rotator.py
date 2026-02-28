from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.tasks.status_rotator import StatusRotator, setup


@pytest.fixture
def bot():
    b = MagicMock()
    b.settings = MagicMock(feature_rotating_status=False)
    b.wait_until_ready = AsyncMock()
    b.change_presence = AsyncMock()
    b.add_cog = AsyncMock()
    return b


@pytest.fixture
def rotator(bot):
    return StatusRotator(bot)


class AsyncCtx:
    def __init__(self, val):
        self.val = val

    async def __aenter__(self):
        return self.val

    async def __aexit__(self, *_):
        pass


def mock_session(resp):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=ctx)
    ctx.__aexit__ = AsyncMock()
    ctx.get = MagicMock(return_value=AsyncCtx(resp))
    return ctx


class TestStatusRotator:
    def test_init(self, bot):
        assert StatusRotator(bot).bot == bot

    @pytest.mark.asyncio
    async def test_setup(self, bot):
        await setup(bot)
        bot.add_cog.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_load_disabled(self, rotator):
        with patch.object(rotator.rotate_status, "start") as m:
            await rotator.cog_load()
            m.assert_not_called()

    @pytest.mark.asyncio
    async def test_cog_load_enabled(self, rotator):
        rotator.bot.settings.feature_rotating_status = True
        with patch.object(rotator.rotate_status, "start") as m:
            await rotator.cog_load()
            m.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload(self, rotator):
        with patch.object(rotator.rotate_status, "cancel") as m:
            await rotator.cog_unload()
            m.assert_called_once()


class TestFetchJoke:
    @pytest.mark.asyncio
    async def test_success(self, rotator):
        resp = AsyncMock(status=200, json=AsyncMock(return_value={"joke": "Test joke"}))
        with patch("aiohttp.ClientSession", return_value=mock_session(resp)):
            assert await rotator._fetch_joke() == "Test joke"

    @pytest.mark.asyncio
    async def test_api_error(self, rotator):
        resp = AsyncMock(status=500)
        with patch("aiohttp.ClientSession", return_value=mock_session(resp)):
            assert await rotator._fetch_joke() is None

    @pytest.mark.asyncio
    async def test_empty(self, rotator):
        resp = AsyncMock(status=200, json=AsyncMock(return_value={"joke": ""}))
        with patch("aiohttp.ClientSession", return_value=mock_session(resp)):
            assert await rotator._fetch_joke() is None

    @pytest.mark.asyncio
    async def test_exception(self, rotator):
        with patch("aiohttp.ClientSession", side_effect=Exception()):
            assert await rotator._fetch_joke() is None


class TestRotateStatus:
    @pytest.mark.asyncio
    async def test_success(self, rotator):
        with patch.object(rotator, "_fetch_joke", return_value="Test"):
            await rotator.rotate_status()
            rotator.bot.change_presence.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_joke(self, rotator):
        with patch.object(rotator, "_fetch_joke", return_value=None):
            await rotator.rotate_status()
            rotator.bot.change_presence.assert_not_called()

    @pytest.mark.asyncio
    async def test_truncates(self, rotator):
        with patch.object(rotator, "_fetch_joke", return_value="A" * 200):
            await rotator.rotate_status()
            activity = rotator.bot.change_presence.call_args[1]["activity"]
            assert len(activity.name) <= 128
            assert activity.name.endswith("...")

    @pytest.mark.asyncio
    async def test_presence_error(self, rotator):
        rotator.bot.change_presence = AsyncMock(side_effect=Exception())
        with patch.object(rotator, "_fetch_joke", return_value="Test"):
            await rotator.rotate_status()

    @pytest.mark.asyncio
    async def test_before_rotate(self, rotator):
        await rotator.before_rotate()
        rotator.bot.wait_until_ready.assert_called_once()
