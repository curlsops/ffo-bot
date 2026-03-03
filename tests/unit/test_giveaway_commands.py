import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.giveaway import (
    AlreadyJoinedView,
    EntriesPaginatedView,
    GiveawayCommands,
    GiveawayView,
    build_embed,
    parse_duration,
    _discord_timestamp,
)


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
        "prize": prize,
        "host_id": host_id,
        "donor_id": donor_id,
        "winners_count": winners_count,
        "ends_at": datetime.now(timezone.utc) + timedelta(hours=hours),
        "extra_text": kw.get("extra_text"),
        "image_url": kw.get("image_url"),
        **kw,
    }


def _active_giveaway(view, **overrides):
    return {
        "id": view.giveaway_id,
        "is_active": True,
        "bypass_roles": [],
        "required_roles": [],
        "blacklist_roles": [],
        "bonus_roles": {},
        "prize": "Test",
        "host_id": 1,
        "donor_id": None,
        "winners_count": 1,
        "ends_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "extra_text": None,
        "image_url": None,
        **overrides,
    }


def _entries(n):
    return [{"user_id": i, "entries": 1} for i in range(n)]


class TestDiscordTimestamp:
    def test_default_format(self):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = _discord_timestamp(dt)
        assert out.startswith("<t:") and ":R>" in out

    def test_custom_format(self):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = _discord_timestamp(dt, "F")
        assert ":F>" in out

    @pytest.mark.parametrize("fmt", ["t", "T", "d", "D", "f", "F", "R"])
    def test_formats(self, fmt):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        out = _discord_timestamp(dt, fmt)
        assert f":{fmt}>" in out


class TestParseDuration:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("30s", 30),
            ("5m", 300),
            ("2h", 7200),
            ("1d", 86400),
            ("1w", 604800),
            ("1H", 3600),
            ("  1h  ", 3600),
            ("0m", 0),
            ("999d", 999 * 86400),
        ],
    )
    def test_valid(self, inp, expected):
        assert parse_duration(inp) == expected

    @pytest.mark.parametrize("inp", ["abc", "1x", "", "1.5h", "x1h"])
    def test_invalid(self, inp):
        assert parse_duration(inp) is None

    @pytest.mark.parametrize("inp,expected_secs", [("1s", 1), ("60s", 60), ("10m", 600)])
    def test_more_valid(self, inp, expected_secs):
        assert parse_duration(inp) == expected_secs

    def test_1w_uppercase(self):
        assert parse_duration("1W") == 604800

    def test_59s_below_min(self):
        assert parse_duration("59s") == 59


class TestParseHelpers:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, []),
            ("", []),
            ("not a role", []),
            ("<@&123> <@&456>", [123, 456]),
        ],
    )
    def test_parse_roles(self, cog, inp, expected):
        assert cog._parse_roles(inp) == expected

    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, {}),
            ("", {}),
            ("<@&123>:5,<@&456>:10", {"123": 5, "456": 10}),
            ("<@&123>:abc,<@&456>:10", {"456": 10}),
            ("<@&123>:-5", {}),
        ],
    )
    def test_parse_bonus_roles(self, cog, inp, expected):
        assert cog._parse_bonus_roles(inp) == expected

    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, None),
            ("", None),
            ("invalid", None),
            ("100", None),
            ("10,<#123>,extra", None),
            ("abc,<#123>", None),
            ("10,notachannel", None),
            ("100,<#789>", {"count": 100, "channel_id": 789}),
        ],
    )
    def test_parse_messages(self, cog, inp, expected):
        assert cog._parse_messages(inp) == expected


class TestBuildEmbed:
    def test_basic(self):
        embed = build_embed(_giveaway(prize="Test Prize"), 0)
        assert embed.title == "🎉 GIVEAWAY 🎉" and "Test Prize" in embed.description

    def test_with_extras(self):
        embed = build_embed(
            _giveaway(donor_id=456, extra_text="Extra info", image_url="https://x.com/a.png"), 10
        )
        assert "<@456>" in embed.description and "Extra info" in embed.description

    def test_ended(self):
        assert (
            "ENDED"
            in build_embed(
                _giveaway(hours=-1, ended_at=datetime.now(timezone.utc)), 5, ended=True
            ).title
        )

    def test_ended_uses_ended_at(self):
        ended_at = datetime.now(timezone.utc)
        g = _giveaway()
        g["ended_at"] = ended_at
        embed = build_embed(g, 3, ended=True)
        assert "ENDED" in embed.title and "3 entries" in embed.footer.text

    def test_ended_with_winners_count(self):
        embed = build_embed(_giveaway(winners_count=2), 10, ended=True)
        assert "2 winners" in embed.footer.text and "10 entries" in embed.footer.text


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
        i = _interaction()
        await cog.giveaway_group.start_cmd.callback(cog.giveaway_group, i, duration, winners, prize)
        assert expected in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        await cog.giveaway_group.start_cmd.callback(cog.giveaway_group, i, "1h", 1, "Prize")
        assert "Admin" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_success(self, cog):
        cog.bot.db_pool = _db_ctx(AsyncMock())
        i = _interaction()
        await cog.giveaway_group.start_cmd.callback(cog.giveaway_group, i, "1h", 1, "Prize")
        i.followup.send.assert_called()

    @pytest.mark.asyncio
    async def test_gstart_ping(self, cog):
        cog.bot.db_pool = _db_ctx(AsyncMock())
        cog.bot.notifier = MagicMock(notify_giveaway_created=AsyncMock())
        i = _interaction()
        await cog.giveaway_group.start_cmd.callback(cog.giveaway_group, i, "1h", 1, "Prize", ping=True)
        call = i.followup.send.call_args
        assert call.kwargs.get("content") == "@everyone"

    @pytest.mark.asyncio
    async def test_gstart_error(self, cog):
        cog.bot.db_pool = _db_ctx(AsyncMock(execute=AsyncMock(side_effect=Exception("DB"))))
        i = _interaction()
        await cog.giveaway_group.start_cmd.callback(cog.giveaway_group, i, "1h", 1, "Prize")
        assert "Error starting" in str(i.followup.send.call_args)


class TestGiveawayView:
    @pytest.mark.asyncio
    async def test_get_giveaway(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(
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
        i.user = MagicMock(id=123, roles=[MagicMock(id=r) for r in user_roles])
        g = {
            "bypass_roles": bypass,
            "required_roles": required,
            "blacklist_roles": blacklist,
            "no_donor_win": donor_block,
            "donor_id": 123 if donor_block else None,
        }
        ok, reason = await view._check_eligibility(i, g)
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
        ],
    )
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
        mock_bot.db_pool = _db_ctx(
            AsyncMock(
                fetchval=AsyncMock(return_value=10), fetchrow=AsyncMock(return_value=_giveaway())
            )
        )
        msg = MagicMock(edit=AsyncMock())
        await view._update_embed(msg, view.giveaway_id)
        msg.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_embed_no_giveaway(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(
            AsyncMock(fetchval=AsyncMock(return_value=0), fetchrow=AsyncMock(return_value=None))
        )
        msg = MagicMock(edit=AsyncMock())
        await view._update_embed(msg, view.giveaway_id)
        msg.edit.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "giveaway,expected",
        [
            (None, "not found"),
            ({"is_active": False}, "ended"),
        ],
    )
    async def test_join_button_early_exit(self, view, mock_bot, giveaway, expected):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(return_value=giveaway)))
        i = _interaction()
        await view.join_button(i)
        assert expected in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_not_eligible(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=_active_giveaway(view, blacklist_roles=[111]))
            )
        )
        i = _interaction()
        i.user.roles = [MagicMock(id=111)]
        await view.join_button(i)
        assert "blacklisted" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_already_joined(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=_active_giveaway(view)),
                execute=AsyncMock(side_effect=Exception("dup")),
            )
        )
        i = _interaction()
        await view.join_button(i)
        call = i.followup.send.call_args
        assert "already joined" in str(call).lower()
        assert call.kwargs.get("view") is not None
        assert isinstance(call.kwargs["view"], AlreadyJoinedView)

    @pytest.mark.asyncio
    async def test_join_button_success(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=_active_giveaway(view)),
                execute=AsyncMock(),
                fetchval=AsyncMock(return_value=1),
            )
        )
        i = _interaction()
        await view.join_button(i)
        assert "joined" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_error(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(side_effect=Exception("DB"))))
        i = _interaction()
        await view.join_button(i)
        assert "Error" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "giveaway,entries_rows,expected",
        [
            (None, [], "not found"),
            ({"id": 1}, [], "No entries"),
        ],
    )
    async def test_entries_button_early_exit(
        self, view, mock_bot, giveaway, entries_rows, expected
    ):
        mock_bot.db_pool = _db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value=giveaway),
                fetch=AsyncMock(return_value=entries_rows),
            )
        )
        i = _interaction()
        await view.entries_button(i)
        assert expected in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_entries_button_with_entries(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(
            AsyncMock(
                fetchrow=AsyncMock(return_value={"id": view.giveaway_id}),
                fetch=AsyncMock(
                    return_value=[{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 2}]
                ),
            )
        )
        i = _interaction()
        await view.entries_button(i)
        call = str(i.followup.send.call_args)
        assert "Giveaway Participants" in call and "<@1>" in call and "<@2>" in call

    @pytest.mark.asyncio
    async def test_entries_button_error(self, view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(fetchrow=AsyncMock(side_effect=Exception("DB"))))
        i = _interaction()
        await view.entries_button(i)
        assert "Error" in str(i.followup.send.call_args)


class TestAlreadyJoinedView:
    @pytest.fixture
    def leave_view(self, mock_bot):
        return AlreadyJoinedView(uuid.uuid4(), 999, mock_bot)

    @pytest.mark.asyncio
    async def test_leave_success(self, leave_view, mock_bot):
        conn = AsyncMock(execute=AsyncMock(return_value="DELETE 1"))
        mock_bot.db_pool = _db_ctx(conn)
        i = _interaction()
        i.channel = MagicMock(fetch_message=AsyncMock(return_value=MagicMock(edit=AsyncMock())))
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchrow = AsyncMock(return_value=_giveaway())
        await leave_view.leave_button.callback(i)
        assert "removed" in str(i.followup.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_leave_not_in_giveaway(self, leave_view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(execute=AsyncMock(return_value="DELETE 0")))
        i = _interaction()
        await leave_view.leave_button.callback(i)
        assert "not in" in str(i.followup.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_leave_channel_none(self, leave_view, mock_bot):
        mock_bot.db_pool = _db_ctx(AsyncMock(execute=AsyncMock(return_value="DELETE 1")))
        i = _interaction()
        i.channel = None
        await leave_view.leave_button.callback(i)
        assert "removed" in str(i.followup.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_leave_updates_embed(self, leave_view, mock_bot):
        gid = leave_view.giveaway_id
        conn = AsyncMock(
            execute=AsyncMock(return_value="DELETE 1"),
            fetchval=AsyncMock(return_value=0),
            fetchrow=AsyncMock(return_value=_giveaway()),
        )
        mock_bot.db_pool = _db_ctx(conn)
        msg = MagicMock(edit=AsyncMock())
        i = _interaction()
        i.channel = MagicMock(fetch_message=AsyncMock(return_value=msg))
        await leave_view.leave_button.callback(i)
        msg.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_leave_button_db_error(self, leave_view, mock_bot, caplog):
        caplog.set_level(logging.WARNING, logger="bot.commands.giveaway")
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("DB unavailable"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_bot.db_pool = MagicMock(acquire=MagicMock(return_value=ctx))
        i = _interaction()
        await leave_view.leave_button.callback(i)
        assert "Error leaving" in str(i.followup.send.call_args)
        assert "Leave giveaway error" in caplog.text


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
        view = EntriesPaginatedView(_entries(n))
        out = view._format_page()
        assert expected in out

    def test_row_with_zero_entries(self):
        view = EntriesPaginatedView([{"user_id": 1, "entries": 0}])
        assert view.total_entries == 0 and "<@1>" in view._format_page()

    def test_update_buttons(self):
        view = EntriesPaginatedView(_entries(15))
        view._update_buttons()
        prev_btn = next(c for c in view.children if c.custom_id == "entries:prev")
        next_btn = next(c for c in view.children if c.custom_id == "entries:next")
        assert prev_btn.disabled and not next_btn.disabled
        view.page = 1
        view._update_buttons()
        assert not prev_btn.disabled and next_btn.disabled

    def test_my_entry_button_shown_when_user_in_list(self):
        view = EntriesPaginatedView(_entries(5), user_id=2)
        my_btn = next((c for c in view.children if c.custom_id == "entries:mine"), None)
        assert my_btn is not None and "My Entry" in my_btn.label

    def test_my_entry_button_hidden_when_user_not_in_list(self):
        view = EntriesPaginatedView(_entries(5), user_id=999)
        my_btn = next((c for c in view.children if c.custom_id == "entries:mine"), None)
        assert my_btn is None

    @pytest.mark.asyncio
    async def test_prev_page_no_op_on_first(self):
        view = EntriesPaginatedView(_entries(15))
        prev_btn = next(c for c in view.children if c.custom_id == "entries:prev")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await prev_btn.callback(i)
        i.response.edit_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_next_page_advances(self):
        view = EntriesPaginatedView(_entries(15))
        next_btn = next(c for c in view.children if c.custom_id == "entries:next")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await next_btn.callback(i)
        assert view.page == 1

    @pytest.mark.asyncio
    async def test_next_page_no_op_on_last(self):
        view = EntriesPaginatedView(_entries(11))
        view.page = 1
        next_btn = next(c for c in view.children if c.custom_id == "entries:next")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await next_btn.callback(i)
        i.response.edit_message.assert_not_called()

    def test_empty_rows(self):
        view = EntriesPaginatedView([])
        assert view.max_page == 0 and view.total_entries == 0
        assert "Giveaway Participants" in view._format_page()

    @pytest.mark.asyncio
    async def test_prev_page_goes_back(self):
        view = EntriesPaginatedView(_entries(15))
        view.page = 1
        prev_btn = next(c for c in view.children if c.custom_id == "entries:prev")
        i = MagicMock(response=MagicMock(edit_message=AsyncMock()))
        await prev_btn.callback(i)
        assert view.page == 0

    @pytest.mark.asyncio
    async def test_my_entry_callback(self):
        view = EntriesPaginatedView([{"user_id": 42, "entries": 3}], user_id=42)
        my_btn = next(c for c in view.children if c.custom_id == "entries:mine")
        i = MagicMock(response=MagicMock(send_message=AsyncMock()))
        await my_btn.callback(i)
        msg = i.response.send_message.call_args[0][0]
        assert "3" in msg and "entries" in msg and "chances of winning" in msg


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
        assert "Giveaway Participants" in out

    def test_paginated_view_exactly_11_items(self):
        view = EntriesPaginatedView(_entries(11))
        assert view.max_page == 1
        out = view._format_page()
        assert "Giveaway Participants" in out


class TestParseMessageId:
    def test_raw_id(self, cog):
        assert cog._parse_message_id("123456789012345678") == 123456789012345678

    def test_message_link(self, cog):
        assert (
            cog._parse_message_id("https://discord.com/channels/1/2/123456789012345678")
            == 123456789012345678
        )

    @pytest.mark.parametrize("inp", ["abc", "12.34", "not-a-id", ""])
    def test_invalid(self, cog, inp):
        assert cog._parse_message_id(inp) is None

    def test_strips_whitespace(self, cog):
        assert cog._parse_message_id("  123456789012345678  ") == 123456789012345678


class TestSelectWinners:
    def test_empty_entries(self, cog):
        assert cog._select_winners([], 1) == []

    def test_zero_count(self, cog):
        assert cog._select_winners([{"user_id": 1, "entries": 1}], 0) == []

    def test_returns_requested_count(self, cog):
        entries = [{"user_id": i, "entries": 1} for i in range(10)]
        winners = cog._select_winners(entries, 2)
        assert len(winners) == 2
        assert len(set(winners)) == 2

    def test_weighted_entries(self, cog):
        entries = [{"user_id": 1, "entries": 5}, {"user_id": 2, "entries": 1}]
        winners = cog._select_winners(entries, 1)
        assert len(winners) == 1
        assert winners[0] in (1, 2)


class TestGreroll:
    @pytest.mark.asyncio
    async def test_invalid_message_id(self, cog):
        cog.bot.db_pool = _db_ctx(AsyncMock())
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "invalid")
        assert "Invalid message ID" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_giveaway_not_found(self, cog):
        conn = AsyncMock(fetchrow=AsyncMock(return_value=None))
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678")
        assert "not found" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_giveaway_still_active(self, cog):
        conn = AsyncMock(fetchrow=AsyncMock(return_value={"id": 1, "is_active": True}))
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678")
        assert "still active" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_no_entries(self, cog):
        giveaway = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=giveaway),
            fetch=AsyncMock(return_value=[]),
        )
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678")
        assert "No entries" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_all_entrants_were_winners(self, cog):
        giveaway = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=giveaway),
            fetch=AsyncMock(
                side_effect=[
                    [{"user_id": 1, "entries": 1}],
                    [{"user_id": 1}],
                ]
            ),
        )
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678")
        assert "All entrants were winners" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_greroll_success(self, cog):
        giveaway = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 1,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=giveaway),
            fetch=AsyncMock(
                side_effect=[
                    [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                    [],
                ]
            ),
            execute=AsyncMock(),
            executemany=AsyncMock(),
        )
        cog.bot.db_pool = _db_ctx(conn)
        cog.bot.get_channel = MagicMock(return_value=None)
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678")
        assert "Rerolled" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_greroll_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        cog.bot.db_pool = _db_ctx(AsyncMock())
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678")
        assert "Admin" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_greroll_partial_count(self, cog):
        giveaway = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 3,
            "ended_at": datetime.now(timezone.utc),
        }
        entries = [
            {"user_id": 1, "entries": 1},
            {"user_id": 2, "entries": 1},
            {"user_id": 3, "entries": 1},
            {"user_id": 4, "entries": 1},
        ]
        old_winners = [{"user_id": 1}, {"user_id": 2}, {"user_id": 3}]
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=giveaway),
            fetch=AsyncMock(side_effect=[entries, old_winners]),
            execute=AsyncMock(),
            executemany=AsyncMock(),
        )
        cog.bot.db_pool = _db_ctx(conn)
        cog.bot.get_channel = MagicMock(return_value=None)
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678", 1)
        assert "Rerolled" in str(i.followup.send.call_args)
        executemany_args = conn.executemany.call_args[0][1]
        assert len(executemany_args) == 3

    @pytest.mark.asyncio
    async def test_greroll_count_exceeds_winners(self, cog):
        giveaway = {
            "id": 1,
            "is_active": False,
            "message_id": 123,
            "channel_id": 2,
            "prize": "Prize",
            "winners_count": 2,
            "ended_at": datetime.now(timezone.utc),
        }
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value=giveaway),
            fetch=AsyncMock(
                side_effect=[
                    [{"user_id": 1, "entries": 1}, {"user_id": 2, "entries": 1}],
                    [{"user_id": 1}, {"user_id": 2}],
                ]
            ),
        )
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.giveaway_group.reroll_cmd.callback(cog.giveaway_group, i, "123456789012345678", 5)
        assert "Cannot reroll more than 2" in str(i.followup.send.call_args)


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.giveaway import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
