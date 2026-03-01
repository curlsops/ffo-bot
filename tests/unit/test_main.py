from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import GracefulShutdown


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        bot = MagicMock(close=AsyncMock())
        gs = GracefulShutdown(bot)
        await gs._shutdown(MagicMock(name="SIGTERM"))
        await gs._shutdown(MagicMock(name="SIGTERM"))
        bot.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_handles_close_error(self, caplog):
        bot = MagicMock(close=AsyncMock(side_effect=Exception("close failed")))
        gs = GracefulShutdown(bot)
        await gs._shutdown(MagicMock(name="SIGTERM"))
        assert "close failed" in caplog.text or "Shutdown error" in caplog.text
