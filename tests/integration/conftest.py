from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock


def message_db_pool(fetchval_result=None):
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=fetchval_result)
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock(acquire=acquire)
    return pool, conn


def bot_with_metrics(*, shutting_down=False):
    bot = MagicMock()
    bot.is_shutting_down.return_value = shutting_down
    bot.metrics = MagicMock()
    bot.metrics.messages_processed.labels.return_value.inc = MagicMock()
    return bot
