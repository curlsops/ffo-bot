import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.minecraft_rcon import MinecraftRCONError, WhitelistListMergeResult
from bot.services.whitelist import (
    ResolutionOutcome,
    SubmissionOutcome,
    WhitelistService,
)
from tests.helpers import (
    build_whitelist_service,
    db_pool_with_conn,
    mock_db_conn,
    mock_mojang_port,
    mock_notifier_port,
    mock_permission_checker_port,
    mock_rcon_port,
)


class TestSubmitIgn:
    @pytest.mark.asyncio
    async def test_invalid_format_too_short(self):
        svc = build_whitelist_service()
        result = await svc.submit_ign(
            server_id=1, channel_id=2, message_id=3, author_id=4, content="ab"
        )
        assert result.outcome is SubmissionOutcome.INVALID_FORMAT

    @pytest.mark.asyncio
    async def test_invalid_format_bad_chars(self):
        svc = build_whitelist_service()
        result = await svc.submit_ign(
            server_id=1, channel_id=2, message_id=3, author_id=4, content="with space"
        )
        assert result.outcome is SubmissionOutcome.INVALID_FORMAT

    @pytest.mark.asyncio
    async def test_invalid_format_bad_chars_no_space(self):
        svc = build_whitelist_service()
        result = await svc.submit_ign(
            server_id=1, channel_id=2, message_id=3, author_id=4, content="Steve!"
        )
        assert result.outcome is SubmissionOutcome.INVALID_FORMAT

    @pytest.mark.asyncio
    async def test_not_found(self):
        mojang = mock_mojang_port(profiles={})
        svc = build_whitelist_service(mojang=mojang)
        result = await svc.submit_ign(
            server_id=1, channel_id=2, message_id=3, author_id=4, content="Ghost"
        )
        assert result.outcome is SubmissionOutcome.NOT_FOUND
        assert result.username == "Ghost"

    @pytest.mark.asyncio
    async def test_accepted_inserts_pending_row(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(profiles={"Steve": ("uuid-1", "Steve")})
        svc = build_whitelist_service(db_pool=pool, mojang=mojang)
        result = await svc.submit_ign(
            server_id=1, channel_id=2, message_id=3, author_id=4, content="Steve"
        )
        assert result.outcome is SubmissionOutcome.ACCEPTED
        assert result.username == "Steve"
        assert result.minecraft_uuid == "uuid-1"
        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert 1 in args and 3 in args and "Steve" in args

    @pytest.mark.asyncio
    async def test_accepted_uses_cached_mojang_lookup(self):
        cache = MagicMock()
        cache.get.side_effect = [None, ("uuid-1", "Steve")]
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(profiles={"Steve": ("uuid-1", "Steve")})
        svc = build_whitelist_service(db_pool=pool, mojang=mojang, cache=cache)
        await svc.submit_ign(server_id=1, channel_id=2, message_id=3, author_id=4, content="Steve")
        await svc.submit_ign(server_id=1, channel_id=2, message_id=5, author_id=4, content="Steve")
        mojang.get_profile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_failure_still_accepted(self, caplog):
        caplog.set_level(logging.ERROR, logger="bot.services.whitelist")
        conn = mock_db_conn()
        conn.execute.side_effect = Exception("db down")
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(profiles={"Steve": ("uuid-1", "Steve")})
        svc = build_whitelist_service(db_pool=pool, mojang=mojang)
        result = await svc.submit_ign(
            server_id=1, channel_id=2, message_id=3, author_id=4, content="Steve"
        )
        assert result.outcome is SubmissionOutcome.ACCEPTED
        assert "Whitelist pending insert error" in caplog.text


class TestResolveReaction:
    @pytest.mark.asyncio
    async def test_wrong_emoji_not_applicable(self):
        svc = build_whitelist_service()
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji="\U0001f600"
        )
        assert result.outcome is ResolutionOutcome.NOT_APPLICABLE

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        checker = mock_permission_checker_port(allow=False)
        svc = build_whitelist_service(permission_checker=checker)
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        assert result.outcome is ResolutionOutcome.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_no_pending_entry_not_applicable(self):
        conn = mock_db_conn(fetchrow=None)
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        assert result.outcome is ResolutionOutcome.NOT_APPLICABLE

    @pytest.mark.asyncio
    async def test_reject_discards_without_rcon_or_notify(self):
        row = {
            "username": "Steve",
            "channel_id": 2,
            "author_id": 4,
            "minecraft_uuid": "uuid-1",
        }
        conn = mock_db_conn(fetchrow=row)
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port()
        notifier = mock_notifier_port()
        svc = build_whitelist_service(db_pool=pool, rcon=rcon, notifier=notifier)
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.REJECT_EMOJI
        )
        assert result.outcome is ResolutionOutcome.REJECTED
        assert result.username == "Steve"
        assert result.channel_id == 2
        assert result.author_id == 4
        rcon.whitelist_add.assert_not_awaited()
        notifier.notify_whitelist.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_approve_calls_rcon_cache_and_notify(self):
        row = {
            "username": "Steve",
            "channel_id": 2,
            "author_id": 4,
            "minecraft_uuid": "uuid-1",
        }
        conn = mock_db_conn(fetchrow=row)
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(whitelist_add="Added Steve")
        notifier = mock_notifier_port()
        svc = build_whitelist_service(db_pool=pool, rcon=rcon, notifier=notifier)
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        assert result.outcome is ResolutionOutcome.APPROVED
        assert result.username == "Steve"
        assert result.author_id == 4
        assert result.channel_id == 2
        assert result.rcon_response == "Added Steve"
        rcon.whitelist_add.assert_awaited_once_with("Steve")
        notifier.notify_whitelist.assert_awaited_once()
        call = notifier.notify_whitelist.call_args
        assert call.args[0] == 1
        assert call.kwargs.get("username") == "Steve"

    @pytest.mark.asyncio
    async def test_approve_notify_fires_before_returning_approved(self):
        # Regression test for the motivating bug: notify must fire on every APPROVED outcome.
        row = {"username": "Steve", "channel_id": 2, "author_id": 4, "minecraft_uuid": "uuid-1"}
        conn = mock_db_conn(fetchrow=row)
        pool = db_pool_with_conn(conn)
        notifier = mock_notifier_port()
        svc = build_whitelist_service(db_pool=pool, notifier=notifier)
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        if result.outcome is ResolutionOutcome.APPROVED:
            notifier.notify_whitelist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_backfills_missing_uuid(self):
        row = {"username": "Steve", "channel_id": 2, "author_id": 4, "minecraft_uuid": None}
        conn = mock_db_conn(fetchrow=row)
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(profiles={"Steve": ("uuid-2", "Steve")})
        svc = build_whitelist_service(db_pool=pool, mojang=mojang)
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        assert result.outcome is ResolutionOutcome.APPROVED
        mojang.get_profile.assert_awaited_once_with("Steve")

    @pytest.mark.asyncio
    async def test_approve_rcon_failure_returns_approve_failed(self):
        row = {"username": "Steve", "channel_id": 2, "author_id": 4, "minecraft_uuid": "uuid-1"}
        conn = mock_db_conn(fetchrow=row)
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(whitelist_add_error=MinecraftRCONError("down"))
        notifier = mock_notifier_port()
        svc = build_whitelist_service(db_pool=pool, rcon=rcon, notifier=notifier)
        result = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        assert result.outcome is ResolutionOutcome.APPROVE_FAILED
        assert result.username == "Steve"
        assert "down" in result.error
        notifier.notify_whitelist.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolve_reaction_is_idempotent(self):
        conn = mock_db_conn(fetchrow=None)
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        first = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        second = await svc.resolve_reaction(
            server_id=1, message_id=2, moderator_id=3, emoji=WhitelistService.APPROVE_EMOJI
        )
        assert first.outcome is ResolutionOutcome.NOT_APPLICABLE
        assert second.outcome is ResolutionOutcome.NOT_APPLICABLE


class TestGetCachedUsernames:
    @pytest.mark.asyncio
    async def test_success(self):
        conn = mock_db_conn(fetch=[{"username": "Alice"}, {"username": "Bob"}])
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        assert await svc.get_cached_usernames(123) == ["Alice", "Bob"]

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        pool = db_pool_with_conn(mock_db_conn())
        cache = MagicMock()
        cache.get.return_value = ["Cached"]
        svc = build_whitelist_service(db_pool=pool, cache=cache)
        assert await svc.get_cached_usernames(123) == ["Cached"]
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_sets_cache(self):
        conn = mock_db_conn(fetch=[{"username": "Alice"}])
        pool = db_pool_with_conn(conn)
        cache = MagicMock()
        cache.get.return_value = None
        svc = build_whitelist_service(db_pool=pool, cache=cache)
        assert await svc.get_cached_usernames(123) == ["Alice"]
        cache.set.assert_called_once_with("whitelist_usernames:123", ["Alice"], ttl=86400)

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        conn = mock_db_conn()
        conn.fetch.side_effect = Exception("DB error")
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        assert await svc.get_cached_usernames(123) == []
        assert "Failed to get whitelist cache" in caplog.text


class TestAddToCache:
    @pytest.mark.asyncio
    async def test_success(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        await svc.add_to_cache(123, "Steve", added_by=456)
        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert 123 in args and "Steve" in args and 456 in args

    @pytest.mark.asyncio
    async def test_invalidates_cache(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        cache = MagicMock()
        svc = build_whitelist_service(db_pool=pool, cache=cache)
        await svc.add_to_cache(123, "Steve")
        cache.delete.assert_called_once_with("whitelist_usernames:123")

    @pytest.mark.asyncio
    async def test_exception_logs(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        conn = mock_db_conn()
        conn.execute.side_effect = Exception("DB error")
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        await svc.add_to_cache(123, "Steve")
        assert "Failed to add to whitelist cache" in caplog.text


class TestRemoveFromCache:
    @pytest.mark.asyncio
    async def test_success(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        await svc.remove_from_cache(123, "Steve")
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidates_cache(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        cache = MagicMock()
        svc = build_whitelist_service(db_pool=pool, cache=cache)
        await svc.remove_from_cache(123, "Steve")
        cache.delete.assert_called_once_with("whitelist_usernames:123")

    @pytest.mark.asyncio
    async def test_exception_logs(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        conn = mock_db_conn()
        conn.execute.side_effect = Exception("DB error")
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        await svc.remove_from_cache(123, "Steve")
        assert "Failed to remove from whitelist cache" in caplog.text


class TestGetCacheEntry:
    @pytest.mark.asyncio
    async def test_success(self):
        u = uuid.UUID("069a79f4-44e9-4726-a5be-fca90e38aaf5")
        conn = mock_db_conn(fetchrow={"username": "Steve", "minecraft_uuid": u})
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        result = await svc.get_cache_entry(1, "Steve")
        assert result["username"] == "Steve"
        assert result["minecraft_uuid"] == "069a79f4-44e9-4726-a5be-fca90e38aaf5"

    @pytest.mark.asyncio
    async def test_not_found(self):
        conn = mock_db_conn(fetchrow=None)
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        assert await svc.get_cache_entry(1, "Nobody") is None

    @pytest.mark.asyncio
    async def test_exception(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        pool = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        pool.acquire.return_value = ctx
        svc = build_whitelist_service(db_pool=pool)
        assert await svc.get_cache_entry(1, "x") is None
        assert "Failed to fetch whitelist cache entry" in caplog.text


class TestReconcileWhitelistCache:
    @pytest.mark.asyncio
    async def test_renames_row_when_uuid_maps_to_new_name(self):
        conn = mock_db_conn(fetch=[{"username": "Old", "minecraft_uuid": uuid.uuid4()}])
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        with patch.object(
            svc.mojang,
            "get_profile_by_uuid",
            AsyncMock(return_value=("069a79f4-44e9-4726-a5be-fca90e38aaf5", "New")),
        ):
            out = await svc.reconcile_whitelist_cache(99)
        assert any("Old → New" in x for x in out["updated"])

    @pytest.mark.asyncio
    async def test_prunes_when_username_has_no_mojang_profile(self):
        conn = mock_db_conn(fetch=[{"username": "Ghost", "minecraft_uuid": None}])
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(profiles={})
        svc = build_whitelist_service(db_pool=pool, mojang=mojang)
        out = await svc.reconcile_whitelist_cache(3)
        assert "Ghost" in out["pruned"]

    @pytest.mark.asyncio
    async def test_backfills_uuid_when_name_valid(self):
        conn = mock_db_conn(fetch=[{"username": "Steve", "minecraft_uuid": None}])
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(
            profiles={"Steve": ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")}
        )
        svc = build_whitelist_service(db_pool=pool, mojang=mojang)
        out = await svc.reconcile_whitelist_cache(3)
        assert "Steve" in out["uuid_filled"]

    @pytest.mark.asyncio
    async def test_no_uuid_row_renamed_via_mojang_lookup(self):
        conn = mock_db_conn(fetch=[{"username": "oldn", "minecraft_uuid": None}])
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(
            profiles={"oldn": ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "NewN")}
        )
        svc = build_whitelist_service(db_pool=pool, mojang=mojang)
        out = await svc.reconcile_whitelist_cache(3)
        assert any("oldn → NewN" in x for x in out["updated"])

    @pytest.mark.asyncio
    async def test_uuid_row_skips_when_session_returns_no_profile(self):
        conn = mock_db_conn(fetch=[{"username": "Steve", "minecraft_uuid": uuid.uuid4()}])
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        with patch.object(svc.mojang, "get_profile_by_uuid", AsyncMock(return_value=None)):
            out = await svc.reconcile_whitelist_cache(3)
        assert out == {"updated": [], "uuid_filled": [], "pruned": []}

    @pytest.mark.asyncio
    async def test_uuid_row_unchanged_when_mojang_name_matches(self):
        u = uuid.uuid4()
        conn = mock_db_conn(fetch=[{"username": "Steve", "minecraft_uuid": u}])
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        with patch.object(
            svc.mojang,
            "get_profile_by_uuid",
            AsyncMock(return_value=("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve")),
        ):
            out = await svc.reconcile_whitelist_cache(3)
        assert out == {"updated": [], "uuid_filled": [], "pruned": []}

    @pytest.mark.asyncio
    async def test_logs_on_fetch_failure(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        conn = mock_db_conn()
        conn.fetch.side_effect = RuntimeError("fetch failed")
        pool = db_pool_with_conn(conn)
        svc = build_whitelist_service(db_pool=pool)
        out = await svc.reconcile_whitelist_cache(3)
        assert out == {"updated": [], "uuid_filled": [], "pruned": []}
        assert "reconcile failed" in caplog.text


class TestSyncFromRcon:
    @pytest.mark.asyncio
    async def test_success(self):
        conn = mock_db_conn()
        conn.executemany = AsyncMock()
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=["Alice", "Bob"],
                reachable_target_ids=("default",),
                unreachable_target_ids=(),
            )
        )
        svc = build_whitelist_service(db_pool=pool, rcon=rcon)
        result = await svc.sync_from_rcon(123)
        assert result.ok
        assert result.player_count == 2
        assert result.reachable_targets == 1
        conn.execute.assert_awaited_once()
        conn.executemany.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidates_cache(self):
        conn = mock_db_conn()
        conn.executemany = AsyncMock()
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=["Alice"], reachable_target_ids=("default",), unreachable_target_ids=()
            )
        )
        cache = MagicMock()
        svc = build_whitelist_service(db_pool=pool, rcon=rcon, cache=cache)
        result = await svc.sync_from_rcon(123)
        assert result.ok
        cache.delete.assert_called_once_with("whitelist_usernames:123")

    @pytest.mark.asyncio
    async def test_uses_batch_fetch_from_mojang_port(self):
        conn = mock_db_conn()
        conn.executemany = AsyncMock()
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=["Steve", "Alex"],
                reachable_target_ids=("default",),
                unreachable_target_ids=(),
            )
        )
        mojang = mock_mojang_port(
            batch={
                "steve": ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Steve"),
                "alex": ("11111111-2222-3333-4444-555555555555", "Alex"),
            }
        )
        svc = build_whitelist_service(db_pool=pool, rcon=rcon, mojang=mojang)
        result = await svc.sync_from_rcon(123)
        assert result.ok
        mojang.get_profiles_batch.assert_awaited_once()
        rows = conn.executemany.call_args.args[1]
        uuids = {row[2] for row in rows}
        assert "069a79f4-44e9-4726-a5be-fca90e38aaf5" in uuids
        assert "11111111-2222-3333-4444-555555555555" in uuids

    @pytest.mark.asyncio
    async def test_empty_username_list(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=[], reachable_target_ids=("default",), unreachable_target_ids=()
            )
        )
        svc = build_whitelist_service(db_pool=pool, rcon=rcon)
        result = await svc.sync_from_rcon(123)
        assert result.ok
        assert result.player_count == 0
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_batch_fetch_exception_still_syncs(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        conn = mock_db_conn()
        conn.executemany = AsyncMock()
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=["Steve"], reachable_target_ids=("default",), unreachable_target_ids=()
            )
        )
        mojang = mock_mojang_port()
        mojang.get_profiles_batch = AsyncMock(side_effect=ValueError("API error"))
        svc = build_whitelist_service(db_pool=pool, rcon=rcon, mojang=mojang)
        result = await svc.sync_from_rcon(123)
        assert result.ok
        assert "Batch UUID fetch failed" in caplog.text

    @pytest.mark.asyncio
    async def test_exception_returns_not_ok(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        conn = mock_db_conn()
        conn.execute.side_effect = Exception("DB error")
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=["Alice"], reachable_target_ids=("default",), unreachable_target_ids=()
            )
        )
        svc = build_whitelist_service(db_pool=pool, rcon=rcon)
        result = await svc.sync_from_rcon(123)
        assert not result.ok
        assert "Failed to sync whitelist from RCON" in caplog.text

    @pytest.mark.asyncio
    async def test_rcon_fails(self):
        pool = db_pool_with_conn(mock_db_conn())
        rcon = mock_rcon_port()
        rcon.whitelist_list_merge = AsyncMock(side_effect=Exception("RCON failed"))
        svc = build_whitelist_service(db_pool=pool, rcon=rcon)
        result = await svc.sync_from_rcon(123)
        assert not result.ok

    @pytest.mark.asyncio
    async def test_no_reachable_targets(self, caplog):
        caplog.set_level(logging.WARNING, logger="bot.services.whitelist")
        pool = db_pool_with_conn(mock_db_conn())
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=[], reachable_target_ids=(), unreachable_target_ids=("a", "b")
            )
        )
        svc = build_whitelist_service(db_pool=pool, rcon=rcon)
        result = await svc.sync_from_rcon(123)
        assert not result.ok
        assert result.unreachable_target_ids == ("a", "b")
        assert "no reachable RCON targets" in caplog.text

    @pytest.mark.asyncio
    async def test_partial_unreachable_carries_ids(self):
        conn = mock_db_conn()
        conn.executemany = AsyncMock()
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port(
            whitelist_list_merge=WhitelistListMergeResult(
                usernames=["Steve"], reachable_target_ids=("good",), unreachable_target_ids=("bad",)
            )
        )
        svc = build_whitelist_service(db_pool=pool, rcon=rcon)
        result = await svc.sync_from_rcon(123)
        assert result.ok
        assert result.unreachable_target_ids == ("bad",)


class TestMetricsEvents:
    @pytest.mark.asyncio
    async def test_submit_ign_accepted_increments_metrics(self):
        conn = mock_db_conn()
        pool = db_pool_with_conn(conn)
        mojang = mock_mojang_port(profiles={"Steve": ("uuid-1", "Steve")})
        metrics = MagicMock()
        metrics.whitelist_events_total.labels = MagicMock(return_value=MagicMock())
        svc = build_whitelist_service(db_pool=pool, mojang=mojang, metrics=metrics)
        result = await svc.submit_ign(
            server_id=1, channel_id=2, message_id=3, author_id=4, content="Steve"
        )
        assert result.outcome is SubmissionOutcome.ACCEPTED
        metrics.whitelist_events_total.labels.assert_called_once_with(
            event="submit", outcome="ACCEPTED"
        )
        metrics.whitelist_events_total.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_reaction_rejected_increments_metrics(self):
        conn = mock_db_conn()
        conn.fetchrow = AsyncMock(
            return_value={
                "username": "Steve",
                "channel_id": 2,
                "author_id": 4,
                "minecraft_uuid": "uuid-1",
            }
        )
        pool = db_pool_with_conn(conn)
        checker = mock_permission_checker_port(allow=True)
        metrics = MagicMock()
        metrics.whitelist_events_total.labels = MagicMock(return_value=MagicMock())
        svc = build_whitelist_service(db_pool=pool, permission_checker=checker, metrics=metrics)
        result = await svc.resolve_reaction(server_id=1, message_id=3, moderator_id=4, emoji="❌")
        assert result.outcome is ResolutionOutcome.REJECTED
        metrics.whitelist_events_total.labels.assert_called_once_with(
            event="reject", outcome="REJECTED"
        )
        metrics.whitelist_events_total.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_reaction_approve_failed_increments_metrics(self):
        conn = mock_db_conn()
        conn.fetchrow = AsyncMock(
            return_value={
                "username": "Steve",
                "channel_id": 2,
                "author_id": 4,
                "minecraft_uuid": "uuid-1",
            }
        )
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port()
        rcon.whitelist_add = AsyncMock(side_effect=Exception("RCON failed"))
        checker = mock_permission_checker_port(allow=True)
        metrics = MagicMock()
        metrics.whitelist_events_total.labels = MagicMock(return_value=MagicMock())
        svc = build_whitelist_service(
            db_pool=pool, rcon=rcon, permission_checker=checker, metrics=metrics
        )
        result = await svc.resolve_reaction(server_id=1, message_id=3, moderator_id=4, emoji="✅")
        assert result.outcome is ResolutionOutcome.APPROVE_FAILED
        metrics.whitelist_events_total.labels.assert_called_once_with(
            event="approve", outcome="APPROVE_FAILED"
        )
        metrics.whitelist_events_total.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_reaction_approved_increments_metrics(self):
        conn = mock_db_conn()
        conn.fetchrow = AsyncMock(
            return_value={
                "username": "Steve",
                "channel_id": 2,
                "author_id": 4,
                "minecraft_uuid": "uuid-1",
            }
        )
        conn.execute = AsyncMock()
        pool = db_pool_with_conn(conn)
        rcon = mock_rcon_port()
        rcon.whitelist_add = AsyncMock(return_value="Added")
        notifier = mock_notifier_port()
        notifier.notify_whitelist = AsyncMock(return_value=True)
        checker = mock_permission_checker_port(allow=True)
        metrics = MagicMock()
        metrics.whitelist_events_total.labels = MagicMock(return_value=MagicMock())
        svc = build_whitelist_service(
            db_pool=pool,
            rcon=rcon,
            notifier=notifier,
            permission_checker=checker,
            metrics=metrics,
        )
        result = await svc.resolve_reaction(server_id=1, message_id=3, moderator_id=4, emoji="✅")
        assert result.outcome is ResolutionOutcome.APPROVED
        metrics.whitelist_events_total.labels.assert_called_once_with(
            event="approve", outcome="APPROVED"
        )
        metrics.whitelist_events_total.labels.return_value.inc.assert_called_once()
