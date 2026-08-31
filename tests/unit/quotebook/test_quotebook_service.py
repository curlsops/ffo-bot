from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services.quotebook_service import QuotebookService


def _make_db_pool(
    fetchval_result=None, fetchrow_result=None, fetch_result=None, execute_result=None
):
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=fetchval_result)
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    conn.fetch = AsyncMock(return_value=fetch_result if fetch_result is not None else [])
    conn.execute = AsyncMock(return_value=execute_result)

    @asynccontextmanager
    async def acquire(**kwargs):
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


class TestListQuoteIds:
    @pytest.mark.asyncio
    async def test_returns_raw_fetch_result(self):
        pool, conn = _make_db_pool(fetch_result=[{"id": 1, "quote_text": "a", "approved": True}])
        service = QuotebookService(pool)
        result = await service.list_quote_ids(1)
        assert result == conn.fetch.return_value
        args = conn.fetch.call_args.args
        assert args[1:] == (1,)


class TestListPendingQuoteIds:
    @pytest.mark.asyncio
    async def test_returns_raw_fetch_result(self):
        pool, conn = _make_db_pool(fetch_result=[{"id": 2, "quote_text": "b"}])
        service = QuotebookService(pool)
        result = await service.list_pending_quote_ids(1)
        assert result == conn.fetch.return_value
        args = conn.fetch.call_args.args
        assert args[1:] == (1,)


class TestSubmitQuote:
    @pytest.mark.asyncio
    async def test_returns_id_string(self):
        pool, conn = _make_db_pool(fetchrow_result={"id": "abc-123"})
        service = QuotebookService(pool)
        result = await service.submit_quote(1, "text", 2, "attr")
        assert result == "abc-123"
        args = conn.fetchrow.call_args.args
        assert args[1:] == (1, "text", 2, "attr")

    @pytest.mark.asyncio
    async def test_invalidates_cache(self):
        pool, conn = _make_db_pool(fetchrow_result={"id": "x"})
        service = QuotebookService(pool)
        cache = MagicMock()
        await service.submit_quote(1, "text", 2, None, cache=cache)
        assert cache.delete.call_count >= 4

    @pytest.mark.asyncio
    async def test_no_cache_is_safe(self):
        pool, conn = _make_db_pool(fetchrow_result={"id": "x"})
        service = QuotebookService(pool)
        await service.submit_quote(1, "text", 2, None)


class TestListAllQuotes:
    @pytest.mark.asyncio
    async def test_returns_dicts(self):
        pool, conn = _make_db_pool(
            fetch_result=[{"id": 1, "quote_text": "a", "attribution": None, "approved": True}]
        )
        service = QuotebookService(pool)
        result = await service.list_all_quotes(1)
        assert result == [{"id": 1, "quote_text": "a", "attribution": None, "approved": True}]
        args = conn.fetch.call_args.args
        assert args[1:] == (1,)


class TestApproveQuote:
    @pytest.mark.asyncio
    async def test_returns_row_on_success(self):
        pool, conn = _make_db_pool(fetchrow_result={"quote_text": "Hello", "attribution": "Me"})
        service = QuotebookService(pool)
        result = await service.approve_quote("qid", 1)
        assert result == {"quote_text": "Hello", "attribution": "Me"}
        args = conn.fetchrow.call_args.args
        assert args[1:] == ("qid", 1)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool, conn = _make_db_pool(fetchrow_result=None)
        service = QuotebookService(pool)
        result = await service.approve_quote("qid", 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self):
        pool, conn = _make_db_pool(fetchrow_result={"quote_text": "H", "attribution": None})
        service = QuotebookService(pool)
        cache = MagicMock()
        await service.approve_quote("qid", 1, cache=cache)
        assert cache.delete.call_count >= 4

    @pytest.mark.asyncio
    async def test_no_invalidation_when_not_found(self):
        pool, conn = _make_db_pool(fetchrow_result=None)
        service = QuotebookService(pool)
        cache = MagicMock()
        await service.approve_quote("qid", 1, cache=cache)
        cache.delete.assert_not_called()


class TestDeleteQuote:
    @pytest.mark.asyncio
    async def test_executes_delete(self):
        pool, conn = _make_db_pool()
        service = QuotebookService(pool)
        await service.delete_quote("qid", 1)
        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert args[1:] == ("qid", 1)

    @pytest.mark.asyncio
    async def test_invalidates_cache(self):
        pool, conn = _make_db_pool()
        service = QuotebookService(pool)
        cache = MagicMock()
        await service.delete_quote("qid", 1, cache=cache)
        assert cache.delete.call_count >= 4


class TestFetchApprovedQuotes:
    @pytest.mark.asyncio
    async def test_no_cache_hits_db(self):
        pool, conn = _make_db_pool(fetch_result=[{"quote_text": "Hi", "attribution": None}])
        service = QuotebookService(pool)
        result = await service.fetch_approved_quotes(1)
        assert result == [{"quote_text": "Hi", "attribution": None}]

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        pool, conn = _make_db_pool()
        service = QuotebookService(pool)
        cache = MagicMock()
        cache.get.return_value = [{"quote_text": "Cached", "attribution": None}]
        result = await service.fetch_approved_quotes(1, cache=cache)
        assert result == [{"quote_text": "Cached", "attribution": None}]
        conn.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_and_sets(self):
        pool, conn = _make_db_pool(fetch_result=[{"quote_text": "Hi", "attribution": None}])
        service = QuotebookService(pool)
        cache = MagicMock()
        cache.get.return_value = None
        result = await service.fetch_approved_quotes(1, cache=cache)
        assert result == [{"quote_text": "Hi", "attribution": None}]
        cache.set.assert_called_once()


class TestImportNewQuotes:
    @pytest.mark.asyncio
    async def test_inserts_new_quotes(self):
        pool, conn = _make_db_pool(fetch_result=[])
        service = QuotebookService(pool)
        quotes = [("Hello", "Me", 10), ("World", None, 11)]
        result = await service.import_new_quotes(1, quotes, True)
        assert result == [("Hello", "Me"), ("World", None)]
        assert conn.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_skips_existing_in_db(self):
        pool, conn = _make_db_pool(fetch_result=[{"quote_text": "Hello"}])
        service = QuotebookService(pool)
        quotes = [("Hello", "Me", 10), ("World", None, 11)]
        result = await service.import_new_quotes(1, quotes, True)
        assert result == [("World", None)]
        assert conn.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_skips_within_batch_duplicates(self):
        pool, conn = _make_db_pool(fetch_result=[])
        service = QuotebookService(pool)
        quotes = [("Hello", "Me", 10), ("Hello", "Other", 11)]
        result = await service.import_new_quotes(1, quotes, True)
        assert result == [("Hello", "Me")]
        assert conn.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_invalidates_cache_unconditionally(self):
        pool, conn = _make_db_pool(fetch_result=[{"quote_text": "Hello"}])
        service = QuotebookService(pool)
        cache = MagicMock()
        await service.import_new_quotes(1, [("Hello", "Me", 10)], True, cache=cache)
        assert cache.delete.call_count >= 4

    @pytest.mark.asyncio
    async def test_empty_quotes(self):
        pool, conn = _make_db_pool(fetch_result=[])
        service = QuotebookService(pool)
        result = await service.import_new_quotes(1, [], True)
        assert result == []
        conn.execute.assert_not_awaited()
