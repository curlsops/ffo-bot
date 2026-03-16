from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers import assert_followup_contains
from tests.unit.giveaway_commands.conftest import OP_REROLL, OP_START, db_ctx, interaction


class TestGiveawayCommands:
    @pytest.mark.asyncio
    async def test_require_admin_success(self, cog):
        from bot.auth.command_helpers import require_admin

        assert await require_admin(interaction(), "test", cog.bot) is True

    @pytest.mark.asyncio
    async def test_require_admin_failure(self, cog):
        from bot.auth.command_helpers import require_admin

        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = interaction()
        assert await require_admin(i, "test", cog.bot) is False
        i.followup.send.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "duration,winners,prize,expected",
        [
            ("invalid", 1, "Prize", "Invalid duration"),
            ("30s", 1, "Prize", "Invalid duration"),
            ("1h", 0, "Prize", "Winners"),
            ("1h", 1, "X" * 600, "Prize max"),
        ],
    )
    async def test_gstart_validation(self, cog, duration, winners, prize, expected):
        i = interaction()
        await cog.giveaway_cmd.callback(
            i, operation=OP_START, duration=duration, winners=winners, prize=prize
        )
        assert_followup_contains(i, expected)

    @pytest.mark.asyncio
    async def test_gstart_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = interaction()
        await cog.giveaway_cmd.callback(
            i, operation=OP_START, duration="1h", winners=1, prize="Prize"
        )
        assert_followup_contains(i, "Admin")

    @pytest.mark.asyncio
    async def test_gstart_success(self, cog):
        cog.bot.db_pool = db_ctx(AsyncMock())
        i = interaction()
        await cog.giveaway_cmd.callback(
            i, operation=OP_START, duration="1h", winners=1, prize="Prize"
        )
        i.followup.send.assert_called()

    @pytest.mark.asyncio
    async def test_gstart_ping(self, cog):
        cog.bot.db_pool = db_ctx(AsyncMock())
        cog.bot.notifier = MagicMock(notify_giveaway_created=AsyncMock())
        i = interaction()
        await cog.giveaway_cmd.callback(
            i, operation=OP_START, duration="1h", winners=1, prize="Prize", ping=True
        )
        call = i.followup.send.call_args
        assert call.kwargs.get("content") == "@everyone"

    @pytest.mark.asyncio
    async def test_gstart_error(self, cog):
        cog.bot.db_pool = db_ctx(AsyncMock(execute=AsyncMock(side_effect=Exception("DB"))))
        i = interaction()
        await cog.giveaway_cmd.callback(
            i, operation=OP_START, duration="1h", winners=1, prize="Prize"
        )
        assert_followup_contains(i, "Error starting")


class TestGreroll:
    @pytest.mark.asyncio
    async def test_invalid_message_id(self, cog):
        cog.bot.db_pool = db_ctx(AsyncMock())
        i = interaction()
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="invalid")
        assert_followup_contains(i, "Invalid message ID")

    @pytest.mark.asyncio
    async def test_giveaway_not_found(self, cog):
        conn = AsyncMock(fetchrow=AsyncMock(return_value=None))
        cog.bot.db_pool = db_ctx(conn)
        i = interaction()
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
        assert_followup_contains(i, "not found")

    @pytest.mark.asyncio
    async def test_giveaway_still_active(self, cog):
        conn = AsyncMock(fetchrow=AsyncMock(return_value={"id": 1, "is_active": True}))
        cog.bot.db_pool = db_ctx(conn)
        i = interaction()
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
        assert_followup_contains(i, "still active")

    @pytest.mark.asyncio
    async def test_no_entries(self, cog):
        current = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(fetchrow=AsyncMock(return_value=current), fetch=AsyncMock(return_value=[]))
        cog.bot.db_pool = db_ctx(conn)
        i = interaction()
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
        assert_followup_contains(i, "No entries")

    @pytest.mark.asyncio
    async def test_all_entrants_were_winners(self, cog):
        current = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=current),
            fetch=AsyncMock(side_effect=[[{"user_id": 1, "entries": 1}], [{"user_id": 1}]]),
        )
        cog.bot.db_pool = db_ctx(conn)
        i = interaction()
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
        assert_followup_contains(i, "All entrants were winners")

    @pytest.mark.asyncio
    async def test_greroll_success(self, cog):
        current = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=current),
            fetch=AsyncMock(
                side_effect=[[{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}], []]
            ),
            execute=AsyncMock(),
            executemany=AsyncMock(),
        )
        cog.bot.db_pool = db_ctx(conn)
        cog.bot.get_channel = MagicMock(return_value=None)
        i = interaction()
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
        assert_followup_contains(i, "Rerolled")

    @pytest.mark.asyncio
    async def test_greroll_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        cog.bot.db_pool = db_ctx(AsyncMock())
        i = interaction()
        await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
        assert_followup_contains(i, "Admin")

    @pytest.mark.asyncio
    async def test_greroll_partial_count(self, cog):
        current = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 3,
            "ended_at": datetime.now(timezone.utc),
        }
        list_entries = [
            {"user_id": 1, "entries": 1},
            {"user_id": 2, "entries": 1},
            {"user_id": 3, "entries": 1},
            {"user_id": 4, "entries": 1},
        ]
        old_winners = [{"user_id": 1}, {"user_id": 2}, {"user_id": 3}]
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=current),
            fetch=AsyncMock(side_effect=[list_entries, old_winners]),
            execute=AsyncMock(),
            executemany=AsyncMock(),
        )
        cog.bot.db_pool = db_ctx(conn)
        cog.bot.get_channel = MagicMock(return_value=None)
        i = interaction()
        await cog.giveaway_cmd.callback(
            i, operation=OP_REROLL, message_id="123456789012345678", count=1
        )
        assert_followup_contains(i, "Rerolled")
        executemany_args = conn.executemany.call_args[0][1]
        assert len(executemany_args) == 3

    @pytest.mark.asyncio
    async def test_greroll_excludes_previous_winners(self, cog):
        current = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 2,
            "ended_at": datetime.now(timezone.utc),
        }
        list_entries = [
            {"user_id": 1, "entries": 1},
            {"user_id": 2, "entries": 1},
            {"user_id": 3, "entries": 1},
        ]
        old_winners = [{"user_id": 1}, {"user_id": 2}]
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=current),
            fetch=AsyncMock(side_effect=[list_entries, old_winners]),
            execute=AsyncMock(),
            executemany=AsyncMock(),
        )
        cog.bot.db_pool = db_ctx(conn)
        cog.bot.get_channel = MagicMock(return_value=None)
        with patch.object(cog, "_select_winners", wraps=cog._select_winners) as mock_select:
            i = interaction()
            await cog.giveaway_cmd.callback(i, operation=OP_REROLL, message_id="123456789012345678")
            pool, _count = mock_select.call_args[0]
            pool_user_ids = {entry["user_id"] for entry in pool}
            assert 1 not in pool_user_ids
            assert 2 not in pool_user_ids
            assert pool_user_ids == {3}

    @pytest.mark.asyncio
    async def test_greroll_count_exceeds_winners(self, cog):
        current = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 2,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=current),
            fetch=AsyncMock(
                side_effect=[
                    [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                    [{"user_id": 1}, {"user_id": 2}],
                ]
            ),
        )
        cog.bot.db_pool = db_ctx(conn)
        i = interaction()
        await cog.giveaway_cmd.callback(
            i, operation=OP_REROLL, message_id="123456789012345678", count=5
        )
        assert_followup_contains(i, "Cannot reroll more than 2")


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.giveaway import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
