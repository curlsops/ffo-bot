import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services.giveaway_repository import GiveawayRepository, get_repository
from tests.helpers import db_pool_with_conn, mock_db_conn


def _ends_at():
    return datetime.now(timezone.utc) + timedelta(hours=1)


class TestInsertGiveaway:
    @pytest.mark.asyncio
    async def test_inserts_with_all_fields(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        giveaway_id = uuid.uuid4()
        ends_at = _ends_at()

        await repo.insert_giveaway(
            id=giveaway_id,
            server_id=1,
            channel_id=2,
            host_id=3,
            donor_id=None,
            prize="A prize",
            winners_count=1,
            ends_at=ends_at,
            required_roles=[],
            blacklist_roles=[],
            bypass_roles=[],
            bonus_roles={},
            message_req=None,
            no_donor_win=False,
            no_defaults=False,
            ping=False,
            extra_text=None,
            image_url=None,
        )

        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert giveaway_id in args
        assert 1 in args
        assert "A prize" in args


class TestSetMessageId:
    @pytest.mark.asyncio
    async def test_updates_message_id(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        giveaway_id = uuid.uuid4()

        await repo.set_message_id(giveaway_id, 555)

        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert 555 in args
        assert giveaway_id in args


class TestFetchByMessageId:
    @pytest.mark.asyncio
    async def test_fetches_from_db(self):
        row = {"id": uuid.uuid4(), "prize": "A prize", "is_active": True}
        conn = mock_db_conn(fetchrow=row)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.fetch_by_message_id(555)

        assert result == row
        conn.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        conn = mock_db_conn(fetchrow=None)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.fetch_by_message_id(555)

        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_cache_on_transient_db_error(self):
        import asyncpg

        conn = mock_db_conn()
        conn.fetchrow.side_effect = asyncpg.CannotConnectNowError("db down")
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        cache = MagicMock()
        cached_row = {"id": uuid.uuid4(), "prize": "Cached"}
        cache.get.return_value = cached_row

        result = await repo.fetch_by_message_id(555, cache=cache)

        assert result == cached_row


class TestFetchById:
    @pytest.mark.asyncio
    async def test_fetches_from_db(self):
        giveaway_id = uuid.uuid4()
        row = {"id": giveaway_id, "prize": "A prize"}
        conn = mock_db_conn(fetchrow=row)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.fetch_by_id(giveaway_id)

        assert result == row

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        conn = mock_db_conn(fetchrow=None)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.fetch_by_id(uuid.uuid4())

        assert result is None


class TestFetchExpired:
    @pytest.mark.asyncio
    async def test_fetches_active_giveaways_past_deadline(self):
        rows = [{"id": uuid.uuid4(), "prize": "A"}, {"id": uuid.uuid4(), "prize": "B"}]
        conn = mock_db_conn(fetch=rows)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        now = datetime.now(timezone.utc)

        result = await repo.fetch_expired(now)

        assert result == rows
        conn.fetch.assert_awaited_once()
        args = conn.fetch.call_args.args
        assert now in args


class TestFetchRecentForAutocomplete:
    @pytest.mark.asyncio
    async def test_fetches_recent_giveaways_for_server(self):
        rows = [{"message_id": 1, "prize": "A", "ended_at": None}]
        conn = mock_db_conn(fetch=rows)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.fetch_recent_for_autocomplete(42)

        assert result == rows
        args = conn.fetch.call_args.args
        assert 42 in args


class TestMarkEnded:
    @pytest.mark.asyncio
    async def test_marks_giveaway_inactive(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        giveaway_id = uuid.uuid4()
        ended_at = datetime.now(timezone.utc)

        await repo.mark_ended(giveaway_id, ended_at)

        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert giveaway_id in args
        assert ended_at in args

    @pytest.mark.asyncio
    async def test_invalidates_cached_giveaway_by_message_id(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        cache = MagicMock()

        await repo.mark_ended(uuid.uuid4(), datetime.now(timezone.utc), cache=cache, message_id=555)

        cache.delete.assert_called_once_with("giveaway:msg:555")


class TestFetchEntries:
    @pytest.mark.asyncio
    async def test_fetches_entries_ordered_by_created_at(self):
        giveaway_id = uuid.uuid4()
        rows = [{"user_id": 1, "entries": 2}, {"user_id": 2, "entries": 1}]
        conn = mock_db_conn(fetch=rows)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.fetch_entries(giveaway_id)

        assert result == rows
        args = conn.fetch.call_args.args
        assert giveaway_id in args


class TestFetchWinnerIds:
    @pytest.mark.asyncio
    async def test_fetches_current_winner_ids(self):
        giveaway_id = uuid.uuid4()
        rows = [{"user_id": 1}, {"user_id": 2}]
        conn = mock_db_conn(fetch=rows)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.fetch_winner_ids(giveaway_id)

        assert result == {1, 2}
        args = conn.fetch.call_args.args
        assert giveaway_id in args


class TestAddEntry:
    @pytest.mark.asyncio
    async def test_inserts_entry_and_returns_true(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.add_entry(giveaway_id, 99, 1)

        assert result is True
        args = conn.execute.call_args.args
        assert giveaway_id in args
        assert 99 in args

    @pytest.mark.asyncio
    async def test_duplicate_entry_returns_false(self, caplog):
        import logging

        caplog.set_level(logging.DEBUG, logger="bot.services.giveaway_repository")
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn()
        conn.execute.side_effect = Exception("duplicate key value")
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.add_entry(giveaway_id, 99, 1)

        assert result is False
        assert "Add entry failed" in caplog.text

    @pytest.mark.asyncio
    async def test_invalidates_entries_cache_on_success(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        cache = MagicMock()

        await repo.add_entry(giveaway_id, 99, 1, cache=cache)

        cache.delete.assert_called_once_with(f"giveaway:entries:{giveaway_id}")


class TestRemoveEntry:
    @pytest.mark.asyncio
    async def test_removes_entry_and_returns_true(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn(execute="DELETE 1")
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.remove_entry(giveaway_id, 99)

        assert result is True
        args = conn.execute.call_args.args
        assert giveaway_id in args
        assert 99 in args

    @pytest.mark.asyncio
    async def test_no_matching_entry_returns_false(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn(execute="DELETE 0")
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.remove_entry(giveaway_id, 99)

        assert result is False

    @pytest.mark.asyncio
    async def test_invalidates_entries_cache_on_success(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn(execute="DELETE 1")
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        cache = MagicMock()

        await repo.remove_entry(giveaway_id, 99, cache=cache)

        cache.delete.assert_called_once_with(f"giveaway:entries:{giveaway_id}")

    @pytest.mark.asyncio
    async def test_does_not_invalidate_cache_when_nothing_removed(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn(execute="DELETE 0")
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)
        cache = MagicMock()

        await repo.remove_entry(giveaway_id, 99, cache=cache)

        cache.delete.assert_not_called()


class TestSetWinners:
    @pytest.mark.asyncio
    async def test_resets_all_then_sets_given_winners(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn()
        conn.executemany = AsyncMock()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        await repo.set_winners(giveaway_id, {1, 2})

        conn.execute.assert_awaited_once()
        reset_args = conn.execute.call_args.args
        assert giveaway_id in reset_args
        conn.executemany.assert_awaited_once()
        rows = conn.executemany.call_args.args[1]
        assert set(rows) == {(giveaway_id, 1), (giveaway_id, 2)}

    @pytest.mark.asyncio
    async def test_empty_winners_only_resets(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn()
        conn.executemany = AsyncMock()
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        await repo.set_winners(giveaway_id, set())

        conn.execute.assert_awaited_once()
        conn.executemany.assert_not_awaited()


class TestCountEntries:
    @pytest.mark.asyncio
    async def test_counts_entries(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn(fetchval=7)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.count_entries(giveaway_id)

        assert result == 7
        args = conn.fetchval.call_args.args
        assert giveaway_id in args

    @pytest.mark.asyncio
    async def test_none_count_returns_zero(self):
        giveaway_id = uuid.uuid4()
        conn = mock_db_conn(fetchval=None)
        pool = db_pool_with_conn(conn)
        repo = GiveawayRepository(pool)

        result = await repo.count_entries(giveaway_id)

        assert result == 0


class TestGetRepository:
    def test_constructs_with_bot_db_pool_and_cache(self):
        bot = MagicMock()
        bot.db_pool = MagicMock()
        bot.cache = MagicMock()

        repo = get_repository(bot)

        assert repo.db_pool is bot.db_pool
        assert repo.cache is bot.cache

    def test_same_bot_returns_same_repository_instance(self):
        bot = MagicMock()

        assert get_repository(bot) is get_repository(bot)

    def test_different_bots_get_different_repository_instances(self):
        bot_a = MagicMock()
        bot_b = MagicMock()

        assert get_repository(bot_a) is not get_repository(bot_b)
