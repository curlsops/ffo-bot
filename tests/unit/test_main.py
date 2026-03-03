import logging
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
        caplog.set_level(logging.ERROR)
        bot = MagicMock(close=AsyncMock(side_effect=Exception("close failed")))
        gs = GracefulShutdown(bot)
        await gs._shutdown(MagicMock(name="SIGTERM"))
        assert any(
            "close failed" in r.message or "Shutdown error" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_shutdown_calls_bot_close(self):
        bot = MagicMock(close=AsyncMock())
        gs = GracefulShutdown(bot)
        await gs._shutdown(MagicMock(name="SIGINT"))
        bot.close.assert_awaited_once()
