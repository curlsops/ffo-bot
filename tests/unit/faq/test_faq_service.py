from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services.faq_service import FaqService


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


class TestInvalidate:
    def test_no_cache_is_safe(self):
        pool, conn = _make_db_pool()
        service = FaqService(pool)
        service._invalidate(None, 1, "rules")

    def test_without_topic_skips_entry_key(self):
        pool, conn = _make_db_pool()
        service = FaqService(pool)
        cache = MagicMock()
        service._invalidate(cache, 1, None)
        assert cache.delete.call_count == 2

    def test_with_topic_deletes_entry_key_too(self):
        pool, conn = _make_db_pool()
        service = FaqService(pool)
        cache = MagicMock()
        service._invalidate(cache, 1, "rules")
        assert cache.delete.call_count == 3


class TestListTopics:
    @pytest.mark.asyncio
    async def test_returns_raw_fetch_result(self):
        pool, conn = _make_db_pool(fetch_result=[{"topic": "rules"}])
        service = FaqService(pool)
        result = await service.list_topics(1)
        assert result == conn.fetch.return_value
        args = conn.fetch.call_args.args
        assert args[1:] == (1,)


class TestFetchEntry:
    @pytest.mark.asyncio
    async def test_no_cache_hits_db(self):
        pool, conn = _make_db_pool(fetchrow_result={"question": "Q", "answer": "A"})
        service = FaqService(pool)
        result = await service.fetch_entry(1, "rules")
        assert result == {"question": "Q", "answer": "A"}
        args = conn.fetchrow.call_args.args
        assert args[1:] == (1, "rules")

    @pytest.mark.asyncio
    async def test_not_found(self):
        pool, conn = _make_db_pool(fetchrow_result=None)
        service = FaqService(pool)
        result = await service.fetch_entry(1, "rules")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        pool, conn = _make_db_pool()
        service = FaqService(pool)
        cache = MagicMock()
        cache.get.return_value = {"question": "Cached", "answer": "A"}
        result = await service.fetch_entry(1, "rules", cache=cache)
        assert result == {"question": "Cached", "answer": "A"}
        conn.fetchrow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_and_sets(self):
        pool, conn = _make_db_pool(fetchrow_result={"question": "Q", "answer": "A"})
        service = FaqService(pool)
        cache = MagicMock()
        cache.get.return_value = None
        result = await service.fetch_entry(1, "rules", cache=cache)
        assert result == {"question": "Q", "answer": "A"}
        cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_not_set_when_not_found(self):
        pool, conn = _make_db_pool(fetchrow_result=None)
        service = FaqService(pool)
        cache = MagicMock()
        cache.get.return_value = None
        result = await service.fetch_entry(1, "rules", cache=cache)
        assert result is None
        cache.set.assert_not_called()


class TestFetchAllEntries:
    @pytest.mark.asyncio
    async def test_no_cache_hits_db(self):
        pool, conn = _make_db_pool(fetch_result=[{"topic": "a", "question": "q", "answer": "z"}])
        service = FaqService(pool)
        result = await service.fetch_all_entries(1)
        assert result == [{"topic": "a", "question": "q", "answer": "z"}]

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        pool, conn = _make_db_pool()
        service = FaqService(pool)
        cache = MagicMock()
        cache.get.return_value = [{"topic": "cached"}]
        result = await service.fetch_all_entries(1, cache=cache)
        assert result == [{"topic": "cached"}]
        conn.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_and_sets(self):
        pool, conn = _make_db_pool(fetch_result=[{"topic": "a"}])
        service = FaqService(pool)
        cache = MagicMock()
        cache.get.return_value = None
        result = await service.fetch_all_entries(1, cache=cache)
        assert result == [{"topic": "a"}]
        cache.set.assert_called_once()


class TestSubmitQuestion:
    @pytest.mark.asyncio
    async def test_returns_id_string(self):
        pool, conn = _make_db_pool(fetchrow_result={"id": "abc-123"})
        service = FaqService(pool)
        result = await service.submit_question(1, "question", 2)
        assert result == "abc-123"
        args = conn.fetchrow.call_args.args
        assert args[1:] == (1, "question", 2)


class TestCountEntries:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        pool, conn = _make_db_pool(fetchval_result=5)
        service = FaqService(pool)
        result = await service.count_entries(1)
        assert result == 5
        args = conn.fetchval.call_args.args
        assert args[1:] == (1,)


class TestUpsertEntry:
    @pytest.mark.asyncio
    async def test_executes_upsert(self):
        pool, conn = _make_db_pool()
        service = FaqService(pool)
        await service.upsert_entry(1, "rules", "Q?", "A.")
        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert args[1:] == (1, "rules", "Q?", "A.")

    @pytest.mark.asyncio
    async def test_invalidates_cache_with_topic(self):
        pool, conn = _make_db_pool()
        service = FaqService(pool)
        cache = MagicMock()
        await service.upsert_entry(1, "rules", "Q?", "A.", cache=cache)
        assert cache.delete.call_count == 3


class TestEditEntry:
    @pytest.mark.asyncio
    async def test_returns_row_on_success(self):
        pool, conn = _make_db_pool(fetchrow_result={"question": "New Q", "answer": "Old A"})
        service = FaqService(pool)
        result = await service.edit_entry(1, "rules", "New Q", None)
        assert result == {"question": "New Q", "answer": "Old A"}
        args = conn.fetchrow.call_args.args
        assert args[1:] == ("New Q", None, 1, "rules")

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool, conn = _make_db_pool(fetchrow_result=None)
        service = FaqService(pool)
        result = await service.edit_entry(1, "rules", "Q", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self):
        pool, conn = _make_db_pool(fetchrow_result={"question": "Q", "answer": "A"})
        service = FaqService(pool)
        cache = MagicMock()
        await service.edit_entry(1, "rules", "Q", None, cache=cache)
        assert cache.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_no_invalidation_when_not_found(self):
        pool, conn = _make_db_pool(fetchrow_result=None)
        service = FaqService(pool)
        cache = MagicMock()
        await service.edit_entry(1, "rules", "Q", None, cache=cache)
        cache.delete.assert_not_called()


class TestListSubmissions:
    @pytest.mark.asyncio
    async def test_returns_dicts(self):
        pool, conn = _make_db_pool(
            fetch_result=[{"id": 1, "question": "q", "submitter_id": 2, "created_at": None}]
        )
        service = FaqService(pool)
        result = await service.list_submissions(1)
        assert result == [{"id": 1, "question": "q", "submitter_id": 2, "created_at": None}]
        args = conn.fetch.call_args.args
        assert args[1:] == (1,)


class TestDeleteEntry:
    @pytest.mark.asyncio
    async def test_true_when_row_deleted(self):
        pool, conn = _make_db_pool(execute_result="DELETE 1")
        service = FaqService(pool)
        result = await service.delete_entry(1, "rules")
        assert result is True
        args = conn.execute.call_args.args
        assert args[1:] == (1, "rules")

    @pytest.mark.asyncio
    async def test_false_when_no_row(self):
        pool, conn = _make_db_pool(execute_result="DELETE 0")
        service = FaqService(pool)
        result = await service.delete_entry(1, "rules")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self):
        pool, conn = _make_db_pool(execute_result="DELETE 1")
        service = FaqService(pool)
        cache = MagicMock()
        await service.delete_entry(1, "rules", cache=cache)
        assert cache.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_no_invalidation_when_not_found(self):
        pool, conn = _make_db_pool(execute_result="DELETE 0")
        service = FaqService(pool)
        cache = MagicMock()
        await service.delete_entry(1, "rules", cache=cache)
        cache.delete.assert_not_called()
