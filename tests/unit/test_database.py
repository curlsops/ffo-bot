from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database.connection import DatabasePool


class TestDatabasePoolCreate:
    @pytest.mark.asyncio
    async def test_create_failure_raises(self):
        with patch("database.connection.asyncpg.create_pool", new_callable=AsyncMock) as m:
            m.side_effect = Exception("connection refused")
            with pytest.raises(Exception, match="connection refused"):
                await DatabasePool.create("postgresql://invalid")

    @pytest.mark.asyncio
    async def test_create_success(self):
        mock_pool = MagicMock()
        with patch("database.connection.asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool):
            pool = await DatabasePool.create("postgresql://localhost/test")
            assert pool._pool == mock_pool


class TestDatabasePoolClose:
    @pytest.mark.asyncio
    async def test_close_with_pool(self):
        mock_pool = MagicMock(close=AsyncMock())
        db = DatabasePool(mock_pool)
        await db.close()
        mock_pool.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_when_pool_none(self):
        db = DatabasePool.__new__(DatabasePool)
        db._pool = None
        await db.close()


class TestDatabasePoolMethods:
    @pytest.mark.asyncio
    async def test_execute(self):
        conn = AsyncMock(execute=AsyncMock(return_value="OK"))
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock(acquire=MagicMock(return_value=ctx))
        db = DatabasePool(mock_pool)
        result = await db.execute("SELECT 1")
        assert result == "OK"

    @pytest.mark.asyncio
    async def test_fetchval(self):
        conn = AsyncMock(fetchval=AsyncMock(return_value=42))
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock(acquire=MagicMock(return_value=ctx))
        db = DatabasePool(mock_pool)
        result = await db.fetchval("SELECT 1")
        assert result == 42
