"""Tests for giveaway commands."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.giveaway import (
    EntriesPaginatedView,
    GiveawayCommands,
    GiveawayView,
    build_embed,
    format_time_remaining,
    parse_duration,
)


# --- Fixtures & Helpers ---

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.metrics.commands_executed.labels.return_value = MagicMock()
    return bot


@pytest.fixture
def cog(mock_bot):
    return GiveawayCommands(mock_bot)


@pytest.fixture
def view(mock_bot):
    return GiveawayView(uuid.uuid4(), mock_bot)


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


def _interaction(guild_id=1, channel_id=2, user_id=3, msg_id=123):
    i = MagicMock(guild_id=guild_id, channel_id=channel_id)
    i.user = MagicMock(id=user_id, roles=[])
    i.message = MagicMock(id=msg_id, edit=AsyncMock())
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock(return_value=MagicMock(id=999))
    return i


def _giveaway(prize="Prize", host_id=123, donor_id=None, winners_count=1, hours=1, **kw):
    return {
        "prize": prize, "host_id": host_id, "donor_id": donor_id, "winners_count": winners_count,
        "ends_at": datetime.now(timezone.utc) + timedelta(hours=hours),
        "extra_text": kw.get("extra_text"), "image_url": kw.get("image_url"), **kw,
    }


def _active_giveaway(view, **overrides):
    return {
        "id": view.giveaway_id, "is_active": True, "bypass_roles": [], "required_roles": [],
        "blacklist_roles": [], "bonus_roles": {}, "prize": "Test", "host_id": 1, "donor_id": None,
        "winners_count": 1, "ends_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "extra_text": None, "image_url": None, **overrides,
    }


def _entries(n):
    return [{"user_id": i, "entries": 1} for i in range(n)]


# --- parse_duration ---

class TestParseDuration:
    @pytest.mark.parametrize("inp,expected", [
        ("30s", 30), ("5m", 300), ("2h", 7200), ("1d", 86400), ("1w", 604800),
        ("1H", 3600), ("  1h  ", 3600), ("0m", 0), ("999d", 999 * 86400),
    ])
    def test_valid(self, inp, expected):
        assert parse_duration(inp) == expected

    @pytest.mark.parametrize("inp", ["abc", "1x", ""])
    def test_invalid(self, inp):
        assert parse_duration(inp) is None


# --- format_time_remaining ---

class TestFormatTimeRemaining:
    def test_ended(self):
        assert format_time_remaining(datetime(2020, 1, 1, tzinfo=timezone.utc)) == "Ended"

    @pytest.mark.parametrize("delta,expected", [
        (timedelta(minutes=30), "m"), (timedelta(hours=5), "h"), (timedelta(days=2, hours=3), "d"),
    ])
    def test_future(self, delta, expected):
        assert expected in format_time_remaining(datetime.now(timezone.utc) + delta)


# --- Parse Helpers ---

class TestParseHelpers:
    @pytest.mark.parametrize("inp,expected", [
        (None, []), ("", []), ("not a role", []), ("<@&123> <@&456>", [123, 456]),
    ])
    def test_parse_roles(self, cog, inp, expected):
        assert cog._parse_roles(inp) == expected

    @pytest.mark.parametrize("inp,expected", [
        (None, {}), ("", {}), ("<@&123>:5,<@&456>:10", {"123": 5, "456": 10}),
        ("<@&123>:abc,<@&456>:10", {"456": 10}), ("<@&123>:-5", {}),
    ])
    def test_parse_bonus_roles(self, cog, inp, expected):
        assert cog._parse_bonus_roles(inp) == expected

    @pytest.mark.parametrize("inp,expected", [
        (None, None), ("", None), ("invalid", None), ("100", None),
        ("10,<#123>,extra", None), ("abc,<#123>", None), ("10,notachannel", None),
        ("100,<#789>", {"count": 100, "channel_id": 789}),
    ])
    def test_parse_messages(self, cog, inp, expected):
        assert cog._parse_messages(inp) == expected


# --- build_embed ---

class TestBuildEmbed:
    def test_basic(self):
        embed = build_embed(_giveaway(prize="Test Prize"), 0)
        assert embed.title == "🎉 GIVEAWAY 🎉" and "Test Prize" in embed.description

    def test_with_extras(self):
        embed = build_embed(_giveaway(donor_id=456, extra_text="Extra info", image_url="https://x.com/a.png"), 10)
        fields = str([f.value for f in embed.fields])
        assert "<@456>" in fields and "Extra info" in fields

    def test_ended(self):
        assert "ENDED" in build_embed(_giveaway(hours=-1, ended_at=datetime.now(timezone.utc)), 5, ended=True).title


# --- GiveawayCommands ---

class TestGiveawayCommands:
    @pytest.mark.asyncio
    async def test_check_admin_success(self, cog):
        assert await cog._check_admin(_interaction(), "test") is True

    @pytest.mark.asyncio
    async def test_check_admin_failure(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        assert await cog._check_admin(i, "test") is False
        i.followup.send.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("duration,winners,prize,expected", [
        ("invalid", 1, "Prize", "Invalid duration"), ("30s", 1, "Prize", "Invalid duration"),
        ("1h", 0, "Prize", "Winners"), ("1h", 1, "X" * 600, "Prize max"),
    ])
    async def test_gstart_validation(self, cog, duration, winners, prize, expected):
        i = _interaction()
        await cog.gstart.callback(cog, i, duration, winners, prize)
        assert expected in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        await cog.gstart.callback(cog, i, "1h", 1, "Prize")
        assert "Admin" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_success(self, cog):
        cog.bot.db_pool = _db_ctx(AsyncMock())
        i = _interaction()
        await cog.gstart.callback(cog, i, "1h", 1, "Prize")
        i.followup.send.assert_called()

    @pytest.mark.asyncio
    async def test_gstart_error(self, cog):
        cog.bot.db_pool = _db_ctx(AsyncMock(execute=AsyncMock(side_effect=Exception("DB"))))
        i = _interaction()
        await cog.gstart.callback(cog, i, "1h", 1, "Prize")
        assert "Error starting" in str(i.followup.send.call_args)


# --- GiveawayView ---

class TestGiveawayView:
    @pytest.mark.asyncio
    async def test_get_giveaway(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(return_value={"id": view.giveaway_id})))
        assert await view._get_giveaway(123) is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bypass,blacklist,required,user_roles,donor_block,expected_ok,expected_reason", [
        ([999], [], [], [999], False, True, ""),
        ([], [888], [], [888], False, False, "blacklisted"),
        ([], [], [777], [], False, False, "required"),
        ([], [], [], [], False, True, ""),
        ([], [], [], [], True, False, "Donors"),
        (None, None, None, [], False, True, ""),
    ])
    async def test_check_eligibility(self, view, bypass, blacklist, required, user_roles, donor_block, expected_ok, expected_reason):
        i = MagicMock()
        i.user = MagicMock(id=123, roles=[MagicMock(id=r) for r in user_roles])
        g = {"bypass_roles": bypass, "required_roles": required, "blacklist_roles": blacklist,
             "no_donor_win": donor_block, "donor_id": 123 if donor_block else None}
        ok, reason = await view._check_eligibility(i, g)
        assert ok == expected_ok
        if expected_reason:
            assert expected_reason in reason

    @pytest.mark.parametrize("roles,bonus_roles,expected", [
        ([], {}, 1), ([], None, 1), ([100], {"100": 5}, 6), ([100, 200], {"100": 5, "200": 3}, 9),
    ])
    def test_calculate_entries(self, view, roles, bonus_roles, expected):
        mock_roles = [MagicMock(id=r) for r in roles]
        assert view._calculate_entries(mock_roles, {"bonus_roles": bonus_roles}) == expected

    @pytest.mark.asyncio
    async def test_add_entry_success(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock())
        assert await view._add_entry(uuid.uuid4(), 123, 1) is True

    @pytest.mark.asyncio
    async def test_add_entry_duplicate(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(execute=AsyncMock(side_effect=Exception("dup"))))
        assert await view._add_entry(uuid.uuid4(), 123, 1) is False

    @pytest.mark.asyncio
    async def test_update_embed(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchval=AsyncMock(return_value=10), fetchrow=AsyncMock(return_value=_giveaway())))
        msg = MagicMock(edit=AsyncMock())
        await view._update_embed(msg, view.giveaway_id)
        msg.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_embed_no_giveaway(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchval=AsyncMock(return_value=0), fetchrow=AsyncMock(return_value=None)))
        msg = MagicMock(edit=AsyncMock())
        await view._update_embed(msg, view.giveaway_id)
        msg.edit.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("giveaway,expected", [
        (None, "not found"), ({"is_active": False}, "ended"),
    ])
    async def test_join_button_early_exit(self, view, mock_bot, giveaway, expected):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=giveaway)))
        i = _interaction()
        await view.join_button.callback(i)
        assert expected in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_not_eligible(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=_active_giveaway(view, blacklist_roles=[111]))))
        i = _interaction()
        i.user.roles = [MagicMock(id=111)]
        await view.join_button.callback(i)
        assert "blacklisted" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_already_joined(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=_active_giveaway(view)), execute=AsyncMock(side_effect=Exception("dup"))))
        i = _interaction()
        await view.join_button.callback(i)
        assert "already" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_success(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=_active_giveaway(view)), execute=AsyncMock(), fetchval=AsyncMock(return_value=1)))
        i = _interaction()
        await view.join_button.callback(i)
        assert "joined" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_error(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(side_effect=Exception("DB"))))
        i = _interaction()
        await view.join_button.callback(i)
        assert "Error" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("giveaway,entries_rows,expected", [
        (None, [], "not found"),
        ({"id": 1}, [], "No entries"),
    ])
    async def test_entries_button_early_exit(self, view, mock_bot, giveaway, entries_rows, expected):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=giveaway), fetch=AsyncMock(return_value=entries_rows)))
        i = _interaction()
        await view.entries_button.callback(i)
        assert expected in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_entries_button_with_entries(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(
            fetchrow=AsyncMock(return_value={"id": view.giveaway_id}),
            fetch=AsyncMock(return_value=[{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 2}])
        ))
        i = _interaction()
        await view.entries_button.callback(i)
        call = str(i.followup.send.call_args)
        assert "2 users" in call and "3 total" in call

    @pytest.mark.asyncio
    async def test_entries_button_error(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(side_effect=Exception("DB"))))
        i = _interaction()
        await view.entries_button.callback(i)
        assert "Error" in str(i.followup.send.call_args)


# --- EntriesPaginatedView ---

class TestEntriesPaginatedView:
    @pytest.mark.parametrize("n,expected_users,expected_total,expected_page", [
        (0, "0 users", "0 total", "Page 1/1"),
        (2, "2 users", "2 total", "Page 1/1"),
        (15, "15 users", "15 total", "Page 1/2"),
    ])
    def test_format_page(self, n, expected_users, expected_total, expected_page):
        view = EntriesPaginatedView(_entries(n))
        out = view._format_page()
        assert expected_users in out and expected_total in out and expected_page in out

    def test_row_with_zero_entries(self):
        view = EntriesPaginatedView([{"user_id": 1, "entries": 0}])
        assert view.total_entries == 0 and "(0)" in view._format_page()

    def test_update_buttons(self):
        view = EntriesPaginatedView(_entries(15))
        view._update_buttons()
        assert view.prev_page.disabled and not view.next_page.disabled
        view.page = 1
        view._update_buttons()
        assert not view.prev_page.disabled and view.next_page.disabled

    @pytest.mark.asyncio
    async def test_prev_page_no_op_on_first(self):
        view = EntriesPaginatedView(_entries(15))
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await view.prev_page.callback(i)
        i.response.edit_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_next_page_advances(self):
        view = EntriesPaginatedView(_entries(15))
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await view.next_page.callback(i)
        assert view.page == 1 and "Page 2/2" in i.response.edit_message.call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_prev_page_goes_back(self):
        view = EntriesPaginatedView(_entries(15))
        view.page = 1
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await view.prev_page.callback(i)
        assert view.page == 0 and "Page 1/2" in i.response.edit_message.call_args[1]["content"]


# --- Edge Cases ---

class TestEdgeCases:
    def test_parse_duration_very_large_value(self):
        result = parse_duration("9999999d")
        assert result == 9999999 * 86400

    def test_calculate_entries_very_large_bonus(self, view):
        roles = [MagicMock(id=100)]
        giveaway = {"bonus_roles": {"100": 999999}}
        result = view._calculate_entries(roles, giveaway)
        assert result == 1000000

    def test_calculate_entries_multiple_large_bonuses(self, view):
        roles = [MagicMock(id=100), MagicMock(id=200)]
        giveaway = {"bonus_roles": {"100": 500000, "200": 500000}}
        result = view._calculate_entries(roles, giveaway)
        assert result == 1000001

    def test_paginated_view_exactly_10_items(self):
        view = EntriesPaginatedView(_entries(10))
        assert view.max_page == 0
        out = view._format_page()
        assert "10 users" in out and "Page 1/1" in out

    def test_paginated_view_exactly_11_items(self):
        view = EntriesPaginatedView(_entries(11))
        assert view.max_page == 1
        out = view._format_page()
        assert "11 users" in out and "Page 1/2" in out

    def test_format_time_remaining_zero_seconds(self):
        now = datetime.now(timezone.utc)
        assert format_time_remaining(now) == "Ended"

    def test_format_time_remaining_one_second(self):
        result = format_time_remaining(datetime.now(timezone.utc) + timedelta(seconds=1))
        assert "0m" in result

    def test_format_time_remaining_over_one_day(self):
        result = format_time_remaining(datetime.now(timezone.utc) + timedelta(days=1, hours=1))
        assert "1d" in result


# --- Setup ---

class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.giveaway import setup
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
