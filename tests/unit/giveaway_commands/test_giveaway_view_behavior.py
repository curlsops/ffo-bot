import asyncio
import logging
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.views import giveaway as giveaway_view_module
from bot.views.giveaway import AlreadyJoinedView, EntriesPaginatedView, GiveawayView, build_embed
from tests.helpers import assert_followup_contains
from tests.unit.giveaway_commands.conftest import db_ctx, entries, giveaway, interaction


class TestBuildEmbed:
    def test_basic(self):
        embed = build_embed(giveaway(prize="Test Prize"), 0)
        assert embed.title == "🎉 GIVEAWAY 🎉" and "Test Prize" in embed.description

    def test_with_extras(self):
        embed = build_embed(
            giveaway(donor_id=456, extra_text="Extra info", image_url="https://x.com/a.png"), 10
        )
        assert "<@456>" in embed.description and "Extra info" in embed.description

    def test_ended(self):
        assert (
            "ENDED"
            in build_embed(
                giveaway(hours=-1, ended_at=datetime.now(timezone.utc)), 5, ended=True
            ).title
        )

    def test_ended_uses_ended_at(self):
        ended_at = datetime.now(timezone.utc)
        current = giveaway()
        current["ended_at"] = ended_at
        embed = build_embed(current, 3, ended=True)
        assert "ENDED" in embed.title and "3 entries" in embed.footer.text

    def test_ended_with_winners_count(self):
        embed = build_embed(giveaway(winners_count=2), 10, ended=True)
        assert "2 winners" in embed.footer.text and "10 entries" in embed.footer.text


class TestAlreadyJoinedView:
    @pytest.fixture
    def leave_view(self, mock_bot):
        return AlreadyJoinedView(uuid.uuid4(), 999, mock_bot)

    @pytest.mark.asyncio
    async def test_leave_success(self, leave_view, mock_bot):
        conn = AsyncMock(execute=AsyncMock(return_value="DELETE 1"))
        mock_bot.db_pool = db_ctx(conn)
        i = interaction()
        i.channel = MagicMock(fetch_message=AsyncMock(return_value=MagicMock(edit=AsyncMock())))
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchrow = AsyncMock(return_value=giveaway())
        await leave_view.leave_button.callback(i)
        assert_followup_contains(i, "removed")

    @pytest.mark.asyncio
    async def test_leave_not_in_giveaway(self, leave_view, mock_bot):
        mock_bot.db_pool = db_ctx(AsyncMock(execute=AsyncMock(return_value="DELETE 0")))
        i = interaction()
        await leave_view.leave_button.callback(i)
        assert_followup_contains(i, "not in")

    @pytest.mark.asyncio
    async def test_leave_channel_none(self, leave_view, mock_bot):
        mock_bot.db_pool = db_ctx(AsyncMock(execute=AsyncMock(return_value="DELETE 1")))
        i = interaction()
        i.channel = None
        await leave_view.leave_button.callback(i)
        assert_followup_contains(i, "removed")

    @pytest.mark.asyncio
    async def test_leave_updates_embed(self, leave_view, mock_bot):
        conn = AsyncMock(
            execute=AsyncMock(return_value="DELETE 1"),
            fetchval=AsyncMock(return_value=0),
            fetchrow=AsyncMock(return_value=giveaway()),
        )
        mock_bot.db_pool = db_ctx(conn)
        msg = MagicMock(edit=AsyncMock())
        i = interaction()
        i.channel = MagicMock(fetch_message=AsyncMock(return_value=msg))
        await leave_view.leave_button.callback(i)
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)
        msg.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_leave_update_embed_no_giveaway(self, leave_view, mock_bot, caplog):
        caplog.set_level(logging.WARNING, logger="bot.views.giveaway")
        conn = AsyncMock(
            execute=AsyncMock(return_value="DELETE 1"),
            fetchval=AsyncMock(return_value=0),
            fetchrow=AsyncMock(return_value=None),
        )
        mock_bot.db_pool = db_ctx(conn)
        msg = MagicMock(edit=AsyncMock())
        i = interaction()
        i.channel = MagicMock(fetch_message=AsyncMock(return_value=msg))
        await leave_view.leave_button.callback(i)
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)
        msg.edit.assert_not_called()

    @pytest.mark.asyncio
    async def test_leave_update_embed_edit_raises(self, leave_view, mock_bot, caplog):
        caplog.set_level(logging.DEBUG, logger="bot.views.giveaway")
        conn = AsyncMock(
            execute=AsyncMock(return_value="DELETE 1"),
            fetchval=AsyncMock(return_value=0),
            fetchrow=AsyncMock(return_value=giveaway()),
        )
        mock_bot.db_pool = db_ctx(conn)
        msg = MagicMock(edit=AsyncMock(side_effect=discord.HTTPException(MagicMock(), "")))
        i = interaction()
        i.channel = MagicMock(fetch_message=AsyncMock(return_value=msg))
        await leave_view.leave_button.callback(i)
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)
        assert "Update embed failed" in caplog.text

    @pytest.mark.asyncio
    async def test_leave_button_db_error(self, leave_view, mock_bot, caplog):
        caplog.set_level(logging.WARNING, logger="bot.commands.giveaway")
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("DB unavailable"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_bot.db_pool = MagicMock(acquire=MagicMock(return_value=ctx))
        i = interaction()
        await leave_view.leave_button.callback(i)
        assert_followup_contains(i, "Error leaving")
        assert "Leave giveaway error" in caplog.text

    @pytest.mark.asyncio
    async def test_update_giveaway_embed_schedule_error_logged(self, leave_view, caplog):
        caplog.set_level(logging.WARNING, logger="bot.views.giveaway")
        i = interaction()
        i.channel = MagicMock()
        original = GiveawayView.schedule_embed_refresh
        GiveawayView.schedule_embed_refresh = AsyncMock(side_effect=Exception("boom"))
        try:
            await leave_view._update_giveaway_embed(i)
        finally:
            GiveawayView.schedule_embed_refresh = original
        assert "Could not update giveaway embed" in caplog.text


class TestEntriesPaginatedView:
    @pytest.mark.parametrize(
        "n,expected",
        [
            (0, "Giveaway Participants"),
            (2, "Giveaway Participants"),
            (15, "Giveaway Participants"),
        ],
    )
    def test_format_page(self, n, expected):
        page_view = EntriesPaginatedView(entries(n))
        out = page_view._format_page()
        assert expected in out

    def test_row_with_zero_entries(self):
        page_view = EntriesPaginatedView([{"user_id": 1, "entries": 0}])
        assert page_view.total_entries == 0 and "<@1>" in page_view._format_page()

    def test_update_buttons(self):
        page_view = EntriesPaginatedView(entries(15))
        page_view._update_buttons()
        prev_btn = next(c for c in page_view.children if c.custom_id == "entries:prev")
        next_btn = next(c for c in page_view.children if c.custom_id == "entries:next")
        assert prev_btn.disabled and not next_btn.disabled
        page_view.page = 1
        page_view._update_buttons()
        assert not prev_btn.disabled and next_btn.disabled

    def test_my_entry_button_shown_when_user_in_list(self):
        page_view = EntriesPaginatedView(entries(5), user_id=2)
        my_btn = next((c for c in page_view.children if c.custom_id == "entries:mine"), None)
        assert my_btn is not None and "My Entry" in my_btn.label

    def test_my_entry_button_hidden_when_user_not_in_list(self):
        page_view = EntriesPaginatedView(entries(5), user_id=999)
        my_btn = next((c for c in page_view.children if c.custom_id == "entries:mine"), None)
        assert my_btn is None

    @pytest.mark.asyncio
    async def test_prev_page_no_op_on_first(self):
        page_view = EntriesPaginatedView(entries(15))
        prev_btn = next(c for c in page_view.children if c.custom_id == "entries:prev")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await prev_btn.callback(i)
        i.response.edit_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_next_page_advances(self):
        page_view = EntriesPaginatedView(entries(15))
        next_btn = next(c for c in page_view.children if c.custom_id == "entries:next")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await next_btn.callback(i)
        assert page_view.page == 1

    @pytest.mark.asyncio
    async def test_next_page_no_op_on_last(self):
        page_view = EntriesPaginatedView(entries(11))
        page_view.page = 1
        next_btn = next(c for c in page_view.children if c.custom_id == "entries:next")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await next_btn.callback(i)
        i.response.edit_message.assert_not_called()

    def test_empty_rows(self):
        page_view = EntriesPaginatedView([])
        assert page_view.max_page == 0 and page_view.total_entries == 0
        assert "Giveaway Participants" in page_view._format_page()

    @pytest.mark.asyncio
    async def test_prev_page_goes_back(self):
        page_view = EntriesPaginatedView(entries(15))
        page_view.page = 1
        prev_btn = next(c for c in page_view.children if c.custom_id == "entries:prev")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await prev_btn.callback(i)
        assert page_view.page == 0

    @pytest.mark.asyncio
    async def test_my_entry_callback(self):
        page_view = EntriesPaginatedView([{"user_id": 42, "entries": 3}], user_id=42)
        my_btn = next(c for c in page_view.children if c.custom_id == "entries:mine")
        i = MagicMock(response=MagicMock(send_message=AsyncMock()))
        await my_btn.callback(i)
        msg = i.response.send_message.call_args[0][0]
        assert "3" in msg and "entries" in msg and "chances of winning" in msg

    def test_paginated_view_exactly_10_items(self):
        page_view = EntriesPaginatedView(entries(10))
        assert page_view.max_page == 0
        out = page_view._format_page()
        assert "Giveaway Participants" in out

    def test_paginated_view_exactly_11_items(self):
        page_view = EntriesPaginatedView(entries(11))
        assert page_view.max_page == 1
        out = page_view._format_page()
        assert "Giveaway Participants" in out


class TestScheduledRefreshBranches:
    @pytest.mark.asyncio
    async def test_schedule_embed_refresh_updates_existing_job_fields(self, view, mock_bot):
        lock, jobs = GiveawayView._get_refresh_state(mock_bot)
        giveaway_id = view.giveaway_id
        done_task = asyncio.create_task(asyncio.sleep(0))
        jobs[giveaway_id] = {
            "dirty": False,
            "message": None,
            "channel": None,
            "message_id": None,
            "task": done_task,
        }
        channel = MagicMock()
        message = MagicMock(id=777, channel=channel)

        await GiveawayView.schedule_embed_refresh(
            mock_bot,
            giveaway_id,
            message=message,
        )
        async with lock:
            job = jobs[giveaway_id]
            assert job["dirty"] is True
            assert job["message"] is message
            assert job["channel"] is channel
            assert job["message_id"] == 777
        await done_task

    @pytest.mark.asyncio
    async def test_schedule_embed_refresh_existing_job_without_new_targets(self, view, mock_bot):
        lock, jobs = GiveawayView._get_refresh_state(mock_bot)
        giveaway_id = view.giveaway_id
        done_task = asyncio.create_task(asyncio.sleep(0))
        existing_message = MagicMock(id=555, channel=MagicMock())
        existing_channel = existing_message.channel
        jobs[giveaway_id] = {
            "dirty": False,
            "message": existing_message,
            "channel": existing_channel,
            "message_id": 555,
            "task": done_task,
        }

        await GiveawayView.schedule_embed_refresh(mock_bot, giveaway_id)
        async with lock:
            job = jobs[giveaway_id]
            assert job["dirty"] is True
            assert job["message"] is existing_message
            assert job["channel"] is existing_channel
            assert job["message_id"] == 555
        await done_task

    @pytest.mark.asyncio
    async def test_run_refresh_job_returns_when_job_missing(self, view, mock_bot, monkeypatch):
        monkeypatch.setattr(giveaway_view_module.asyncio, "sleep", AsyncMock(return_value=None))
        lock, jobs = GiveawayView._get_refresh_state(mock_bot)
        jobs.pop(view.giveaway_id, None)
        await GiveawayView._run_refresh_job(mock_bot, view.giveaway_id)

    @pytest.mark.asyncio
    async def test_run_refresh_job_returns_when_job_removed_after_refresh(
        self, view, mock_bot, monkeypatch
    ):
        monkeypatch.setattr(giveaway_view_module.asyncio, "sleep", AsyncMock(return_value=None))
        lock, jobs = GiveawayView._get_refresh_state(mock_bot)
        jobs[view.giveaway_id] = {
            "dirty": False,
            "message": MagicMock(id=1, channel=MagicMock()),
            "channel": MagicMock(),
            "message_id": 1,
            "task": None,
        }

        async def _remove_job(*args, **kwargs):
            async with lock:
                jobs.pop(view.giveaway_id, None)

        original = GiveawayView._refresh_embed_now_with_fallback
        GiveawayView._refresh_embed_now_with_fallback = _remove_job
        try:
            await GiveawayView._run_refresh_job(mock_bot, view.giveaway_id)
        finally:
            GiveawayView._refresh_embed_now_with_fallback = original

    @pytest.mark.asyncio
    async def test_refresh_embed_now_with_fallback_returns_without_target(self, view, mock_bot):
        await GiveawayView._refresh_embed_now_with_fallback(
            mock_bot,
            view.giveaway_id,
            message=None,
            channel=None,
            message_id=None,
        )

    @pytest.mark.asyncio
    async def test_refresh_embed_now_with_fallback_fetch_error(self, view, mock_bot, caplog):
        caplog.set_level(logging.DEBUG, logger="bot.views.giveaway")
        channel = MagicMock(fetch_message=AsyncMock(side_effect=Exception("fetch failed")))
        await GiveawayView._refresh_embed_now_with_fallback(
            mock_bot,
            view.giveaway_id,
            message=None,
            channel=channel,
            message_id=123,
        )
        assert "Could not fetch giveaway message for refresh" in caplog.text

    @pytest.mark.asyncio
    async def test_wait_for_scheduled_refreshes_with_no_tasks(self, mock_bot):
        await GiveawayView.wait_for_scheduled_refreshes(mock_bot)
