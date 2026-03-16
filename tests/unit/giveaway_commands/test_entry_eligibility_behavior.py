import asyncio
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.views import giveaway as giveaway_view_module
from bot.views.giveaway import AlreadyJoinedView, GiveawayView
from tests.helpers import assert_followup_contains
from tests.unit.giveaway_commands.conftest import active_giveaway, db_ctx, giveaway, interaction


class TestGiveawayView:
    @pytest.mark.asyncio
    async def test_get_giveaway(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(fetchrow=AsyncMock(return_value={"id": view.giveaway_id}))
        )
        assert await view._get_giveaway(123) is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bypass,blacklist,required,user_roles,donor_block,expected_ok,expected_reason",
        [
            ([999], [], [], [999], False, True, ""),
            ([], [888], [], [888], False, False, "blacklisted"),
            ([], [], [777], [], False, False, "required"),
            ([], [], [], [], False, True, ""),
            ([], [], [], [], True, False, "Donors"),
            (None, None, None, [], False, True, ""),
        ],
    )
    async def test_check_eligibility(
        self,
        view,
        bypass,
        blacklist,
        required,
        user_roles,
        donor_block,
        expected_ok,
        expected_reason,
    ):
        i = MagicMock()
        i.user = MagicMock(id=123, roles=[MagicMock(id=role_id) for role_id in user_roles])
        current = {
            "bypass_roles": bypass,
            "required_roles": required,
            "blacklist_roles": blacklist,
            "no_donor_win": donor_block,
            "donor_id": 123 if donor_block else None,
        }
        ok, reason = await view._check_eligibility(i, current)
        assert ok == expected_ok
        if expected_reason:
            assert expected_reason in reason

    @pytest.mark.parametrize(
        "roles,bonus_roles,expected",
        [
            ([], {}, 1),
            ([], None, 1),
            ([100], {"100": 5}, 6),
            ([100, 200], {"100": 5, "200": 3}, 9),
            ([100], {"999": 5}, 1),
        ],
    )
    def test_calculate_entries(self, view, roles, bonus_roles, expected):
        mock_roles = [MagicMock(id=role_id) for role_id in roles]
        assert view._calculate_entries(mock_roles, {"bonus_roles": bonus_roles}) == expected

    @pytest.mark.asyncio
    async def test_add_entry_success(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(AsyncMock())
        assert await view._add_entry(uuid.uuid4(), 123, 1) is True

    @pytest.mark.asyncio
    async def test_add_entry_duplicate(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(AsyncMock(execute=AsyncMock(side_effect=Exception("dup"))))
        assert await view._add_entry(uuid.uuid4(), 123, 1) is False

    @pytest.mark.asyncio
    async def test_update_embed(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchval=AsyncMock(return_value=10), fetchrow=AsyncMock(return_value=giveaway())
            )
        )
        msg = MagicMock(edit=AsyncMock())
        await view._update_embed(msg, view.giveaway_id)
        msg.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_embed_no_giveaway(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(fetchval=AsyncMock(return_value=0), fetchrow=AsyncMock(return_value=None))
        )
        msg = MagicMock(edit=AsyncMock())
        await view._update_embed(msg, view.giveaway_id)
        msg.edit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_embed_edit_raises(self, view, mock_bot, caplog):
        caplog.set_level(logging.DEBUG, logger="bot.views.giveaway")
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchval=AsyncMock(return_value=1),
                fetchrow=AsyncMock(return_value=giveaway()),
            )
        )
        msg = MagicMock(edit=AsyncMock(side_effect=discord.HTTPException(MagicMock(), "")))
        await view._update_embed(msg, view.giveaway_id)
        assert "Update embed failed" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "current,expected",
        [
            (None, "not found"),
            ({"is_active": False}, "ended"),
        ],
    )
    async def test_join_button_early_exit(self, view, mock_bot, current, expected):
        mock_bot.db_pool = db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=current)))
        i = interaction()
        await view.join_button(i)
        assert_followup_contains(i, expected)

    @pytest.mark.asyncio
    async def test_join_button_not_eligible(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(fetchrow=AsyncMock(return_value=active_giveaway(view, blacklist_roles=[111])))
        )
        i = interaction()
        i.user.roles = [MagicMock(id=111)]
        await view.join_button(i)
        assert_followup_contains(i, "blacklisted")

    @pytest.mark.asyncio
    async def test_join_button_required_role_missing(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(fetchrow=AsyncMock(return_value=active_giveaway(view, required_roles=[999])))
        )
        i = interaction()
        i.user.roles = []
        await view.join_button(i)
        assert_followup_contains(i, "required")

    @pytest.mark.asyncio
    async def test_join_button_defer_not_found_returns_early(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=active_giveaway(view))))
        i = interaction()
        i.response.defer = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        await view.join_button(i)
        i.followup.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_button_success_with_cache(self, view, mock_bot):
        mock_bot.cache = MagicMock(delete=MagicMock())
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=active_giveaway(view)),
                execute=AsyncMock(),
                fetchval=AsyncMock(return_value=1),
            )
        )
        i = interaction()
        await view.join_button(i)
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)
        mock_bot.cache.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_join_button_success_without_cache(self, view, mock_bot):
        mock_bot.cache = None
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=active_giveaway(view)),
                execute=AsyncMock(),
                fetchval=AsyncMock(return_value=1),
            )
        )
        i = interaction()
        await view.join_button(i)
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)
        assert_followup_contains(i, "joined")

    @pytest.mark.asyncio
    async def test_defer_ephemeral_not_found_returns_false(self, view):
        i = interaction()
        i.response.defer = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        result = await view._defer_ephemeral(i)
        assert result is False

    @pytest.mark.asyncio
    async def test_defer_ephemeral_success_returns_true(self, view):
        i = interaction()
        i.response.defer = AsyncMock()
        result = await view._defer_ephemeral(i)
        assert result is True

    @pytest.mark.asyncio
    async def test_entries_button_defer_not_found_returns_early(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value={"id": view.giveaway_id}),
                fetch=AsyncMock(return_value=[{"user_id": 1, "entries": 1}]),
            )
        )
        i = interaction()
        i.response.defer = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        await view.entries_button(i)
        i.followup.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_button_already_joined(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=active_giveaway(view)),
                execute=AsyncMock(side_effect=Exception("dup")),
            )
        )
        i = interaction()
        await view.join_button(i)
        call = i.followup.send.call_args
        assert_followup_contains(i, "already joined")
        assert isinstance(call.kwargs["view"], AlreadyJoinedView)

    @pytest.mark.asyncio
    async def test_join_button_success(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=active_giveaway(view)),
                execute=AsyncMock(),
                fetchval=AsyncMock(return_value=1),
            )
        )
        i = interaction()
        await view.join_button(i)
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)
        assert_followup_contains(i, "joined")

    @pytest.mark.asyncio
    async def test_schedule_embed_refresh_coalesces_rapid_updates(
        self, view, mock_bot, monkeypatch
    ):
        monkeypatch.setattr(giveaway_view_module, "EMBED_REFRESH_DEBOUNCE_SECONDS", 0)
        conn = AsyncMock(
            fetchval=AsyncMock(return_value=3),
            fetchrow=AsyncMock(return_value=giveaway()),
        )
        mock_bot.db_pool = db_ctx(conn)
        msg = MagicMock(id=123, channel=MagicMock(), edit=AsyncMock())

        await view._schedule_embed_update(msg, view.giveaway_id)
        await view._schedule_embed_update(msg, view.giveaway_id)
        await view._schedule_embed_update(msg, view.giveaway_id)
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)

        msg.edit.assert_called_once()
        assert conn.fetchval.await_count == 1

    @pytest.mark.asyncio
    async def test_schedule_embed_refresh_runs_again_if_marked_dirty_mid_update(
        self, view, mock_bot, monkeypatch
    ):
        monkeypatch.setattr(giveaway_view_module, "EMBED_REFRESH_DEBOUNCE_SECONDS", 0)
        conn = AsyncMock(
            fetchval=AsyncMock(side_effect=[1, 2]),
            fetchrow=AsyncMock(return_value=giveaway()),
        )
        mock_bot.db_pool = db_ctx(conn)

        first_edit_started = asyncio.Event()
        release_first_edit = asyncio.Event()
        call_count = 0

        async def edit_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                first_edit_started.set()
                await release_first_edit.wait()

        msg = MagicMock(id=123, channel=MagicMock(), edit=AsyncMock(side_effect=edit_side_effect))

        await view._schedule_embed_update(msg, view.giveaway_id)
        await asyncio.wait_for(first_edit_started.wait(), timeout=1)
        await view._schedule_embed_update(msg, view.giveaway_id)
        release_first_edit.set()
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)

        assert msg.edit.await_count == 2
        latest_view = msg.edit.call_args_list[-1].kwargs["view"]
        entries_btn = next(c for c in latest_view.children if c.custom_id == "giveaway:entries")
        assert entries_btn.label == "👥 2"

    @pytest.mark.asyncio
    async def test_join_button_error(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(AsyncMock(fetchrow=AsyncMock(side_effect=Exception("DB"))))
        i = interaction()
        await view.join_button(i)
        assert_followup_contains(i, "Error")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "current,entries_rows,expected",
        [
            (None, [], "not found"),
            ({"id": 1}, [], "No entries"),
        ],
    )
    async def test_entries_button_early_exit(self, view, mock_bot, current, entries_rows, expected):
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=current),
                fetch=AsyncMock(return_value=entries_rows),
            )
        )
        i = interaction()
        await view.entries_button(i)
        assert_followup_contains(i, expected)

    @pytest.mark.asyncio
    async def test_entries_button_with_entries(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value={"id": view.giveaway_id}),
                fetch=AsyncMock(
                    return_value=[{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 2}]
                ),
            )
        )
        i = interaction()
        await view.entries_button(i)
        call = i.followup.send.call_args
        content = call.args[0]
        assert "Giveaway Participants" in content
        assert "<@1>" in content and "<@2>" in content

    @pytest.mark.asyncio
    async def test_entries_button_error(self, view, mock_bot):
        mock_bot.db_pool = db_ctx(AsyncMock(fetchrow=AsyncMock(side_effect=Exception("DB"))))
        i = interaction()
        await view.entries_button(i)
        assert_followup_contains(i, "Error")


class TestEntryEdgeCases:
    def test_calculate_entries_very_large_bonus(self, view):
        roles = [MagicMock(id=100)]
        current = {"bonus_roles": {"100": 999999}}
        result = view._calculate_entries(roles, current)
        assert result == 1000000

    def test_calculate_entries_multiple_large_bonuses(self, view):
        roles = [MagicMock(id=100), MagicMock(id=200)]
        current = {"bonus_roles": {"100": 500000, "200": 500000}}
        result = view._calculate_entries(roles, current)
        assert result == 1000001
