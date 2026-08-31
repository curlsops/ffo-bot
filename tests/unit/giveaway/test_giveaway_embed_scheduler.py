import asyncio
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.views import giveaway as giveaway_view_module
from bot.views.giveaway import GiveawayEmbedScheduler, _get_scheduler
from tests.unit.giveaway.conftest import db_ctx, giveaway


class TestGiveawayEmbedScheduler:
    @pytest.mark.asyncio
    async def test_schedule_refresh_debounces_then_updates_embed(self, mock_bot, monkeypatch):
        monkeypatch.setattr(giveaway_view_module, "EMBED_REFRESH_DEBOUNCE_SECONDS", 0)
        conn = AsyncMock(
            fetchval=AsyncMock(return_value=3),
            fetchrow=AsyncMock(return_value=giveaway()),
        )
        mock_bot.db_pool = db_ctx(conn)
        giveaway_id = uuid.uuid4()
        msg = MagicMock(id=123, channel=MagicMock(), edit=AsyncMock())
        scheduler = GiveawayEmbedScheduler()

        await scheduler.schedule_refresh(mock_bot, giveaway_id, message=msg)
        await scheduler.wait_for_scheduled()

        msg.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_rapid_reschedules_coalesce_into_one_refresh_and_job_is_cleaned_up(
        self, mock_bot, monkeypatch
    ):
        monkeypatch.setattr(giveaway_view_module, "EMBED_REFRESH_DEBOUNCE_SECONDS", 0)
        conn = AsyncMock(
            fetchval=AsyncMock(return_value=3),
            fetchrow=AsyncMock(return_value=giveaway()),
        )
        mock_bot.db_pool = db_ctx(conn)
        giveaway_id = uuid.uuid4()
        msg = MagicMock(id=123, channel=MagicMock(), edit=AsyncMock())
        scheduler = GiveawayEmbedScheduler()

        await scheduler.schedule_refresh(mock_bot, giveaway_id, message=msg)
        await scheduler.schedule_refresh(mock_bot, giveaway_id, message=msg)
        await scheduler.schedule_refresh(mock_bot, giveaway_id, message=msg)
        await scheduler.wait_for_scheduled()

        msg.edit.assert_called_once()
        assert conn.fetchval.await_count == 1
        assert giveaway_id not in scheduler._jobs

    @pytest.mark.asyncio
    async def test_schedule_marked_dirty_mid_update_runs_again(self, mock_bot, monkeypatch):
        monkeypatch.setattr(giveaway_view_module, "EMBED_REFRESH_DEBOUNCE_SECONDS", 0)
        conn = AsyncMock(
            fetchval=AsyncMock(side_effect=[1, 2]),
            fetchrow=AsyncMock(return_value=giveaway()),
        )
        mock_bot.db_pool = db_ctx(conn)
        giveaway_id = uuid.uuid4()

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
        scheduler = GiveawayEmbedScheduler()

        await scheduler.schedule_refresh(mock_bot, giveaway_id, message=msg)
        await asyncio.wait_for(first_edit_started.wait(), timeout=1)
        await scheduler.schedule_refresh(mock_bot, giveaway_id, message=msg)
        release_first_edit.set()
        await scheduler.wait_for_scheduled()

        assert msg.edit.await_count == 2
        assert giveaway_id not in scheduler._jobs

    @pytest.mark.asyncio
    async def test_run_refresh_job_returns_when_job_missing(self, mock_bot, monkeypatch):
        monkeypatch.setattr(giveaway_view_module.asyncio, "sleep", AsyncMock(return_value=None))
        giveaway_id = uuid.uuid4()
        scheduler = GiveawayEmbedScheduler()
        await scheduler._run_refresh_job(mock_bot, giveaway_id)
        assert giveaway_id not in scheduler._jobs

    @pytest.mark.asyncio
    async def test_run_refresh_job_returns_when_job_removed_after_refresh(
        self, mock_bot, monkeypatch
    ):
        monkeypatch.setattr(giveaway_view_module.asyncio, "sleep", AsyncMock(return_value=None))
        giveaway_id = uuid.uuid4()
        scheduler = GiveawayEmbedScheduler()
        scheduler._jobs[giveaway_id] = {
            "dirty": False,
            "message": MagicMock(id=1, channel=MagicMock()),
            "channel": MagicMock(),
            "message_id": 1,
            "task": None,
        }

        async def _remove_job(*args, **kwargs):
            scheduler._jobs.pop(giveaway_id, None)

        scheduler._refresh_embed_now_with_fallback = _remove_job
        await scheduler._run_refresh_job(mock_bot, giveaway_id)
        assert giveaway_id not in scheduler._jobs

    @pytest.mark.asyncio
    async def test_refresh_embed_now_with_fallback_returns_without_target(self, mock_bot):
        scheduler = GiveawayEmbedScheduler()
        await scheduler._refresh_embed_now_with_fallback(
            mock_bot,
            uuid.uuid4(),
            message=None,
            channel=None,
            message_id=None,
        )

    @pytest.mark.asyncio
    async def test_refresh_embed_now_with_fallback_fetch_error(self, mock_bot, caplog):
        caplog.set_level(logging.DEBUG, logger="bot.views.giveaway")
        channel = MagicMock(fetch_message=AsyncMock(side_effect=Exception("fetch failed")))
        scheduler = GiveawayEmbedScheduler()
        await scheduler._refresh_embed_now_with_fallback(
            mock_bot,
            uuid.uuid4(),
            message=None,
            channel=channel,
            message_id=123,
        )
        assert "Could not fetch giveaway message for refresh" in caplog.text

    @pytest.mark.asyncio
    async def test_wait_for_scheduled_with_no_tasks(self):
        scheduler = GiveawayEmbedScheduler()
        await scheduler.wait_for_scheduled()

    @pytest.mark.asyncio
    async def test_schedule_refresh_updates_existing_job_fields(self, mock_bot):
        giveaway_id = uuid.uuid4()
        scheduler = GiveawayEmbedScheduler()
        done_task = asyncio.create_task(asyncio.sleep(0))
        scheduler._jobs[giveaway_id] = {
            "dirty": False,
            "message": None,
            "channel": None,
            "message_id": None,
            "task": done_task,
        }
        channel = MagicMock()
        message = MagicMock(id=777, channel=channel)

        await scheduler.schedule_refresh(mock_bot, giveaway_id, message=message)

        job = scheduler._jobs[giveaway_id]
        assert job["dirty"] is True
        assert job["message"] is message
        assert job["channel"] is channel
        assert job["message_id"] == 777
        _ = await done_task

    @pytest.mark.asyncio
    async def test_schedule_refresh_existing_job_without_new_targets(self, mock_bot):
        giveaway_id = uuid.uuid4()
        scheduler = GiveawayEmbedScheduler()
        done_task = asyncio.create_task(asyncio.sleep(0))
        existing_message = MagicMock(id=555, channel=MagicMock())
        existing_channel = existing_message.channel
        scheduler._jobs[giveaway_id] = {
            "dirty": False,
            "message": existing_message,
            "channel": existing_channel,
            "message_id": 555,
            "task": done_task,
        }

        await scheduler.schedule_refresh(mock_bot, giveaway_id)

        job = scheduler._jobs[giveaway_id]
        assert job["dirty"] is True
        assert job["message"] is existing_message
        assert job["channel"] is existing_channel
        assert job["message_id"] == 555
        _ = await done_task


class TestGetScheduler:
    def test_same_bot_returns_same_scheduler_instance(self, mock_bot):
        assert _get_scheduler(mock_bot) is _get_scheduler(mock_bot)

    def test_different_bots_get_different_scheduler_instances(self, mock_bot):
        other_bot = MagicMock()
        assert _get_scheduler(mock_bot) is not _get_scheduler(other_bot)
