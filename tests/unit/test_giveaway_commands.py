"""Tests for giveaway commands."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.giveaway import (
    GiveawayCommands,
    GiveawayView,
    format_time_remaining,
    parse_duration,
)


class TestParseDuration:
    def test_seconds(self):
        assert parse_duration("30s") == 30

    def test_minutes(self):
        assert parse_duration("5m") == 300

    def test_hours(self):
        assert parse_duration("2h") == 7200

    def test_days(self):
        assert parse_duration("1d") == 86400

    def test_weeks(self):
        assert parse_duration("1w") == 604800

    def test_case_insensitive(self):
        assert parse_duration("1H") == 3600

    def test_invalid(self):
        assert parse_duration("abc") is None
        assert parse_duration("1x") is None
        assert parse_duration("") is None


class TestFormatTimeRemaining:
    def test_ended(self):
        past = datetime.now(timezone.utc).replace(year=2020)
        assert format_time_remaining(past) == "Ended"

    def test_minutes(self):
        from datetime import timedelta
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        result = format_time_remaining(future)
        assert "m" in result

    def test_hours(self):
        from datetime import timedelta
        future = datetime.now(timezone.utc) + timedelta(hours=5)
        result = format_time_remaining(future)
        assert "h" in result

    def test_days(self):
        from datetime import timedelta
        future = datetime.now(timezone.utc) + timedelta(days=2, hours=3)
        result = format_time_remaining(future)
        assert "d" in result


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.metrics = MagicMock()
    bot.metrics.commands_executed = MagicMock()
    bot.metrics.commands_executed.labels = MagicMock(return_value=MagicMock())
    return bot


@pytest.fixture
def cog(mock_bot):
    return GiveawayCommands(mock_bot)


def make_db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


class TestGiveawayCommandsParseHelpers:
    def test_parse_roles_empty(self, cog):
        assert cog._parse_roles(None) == []
        assert cog._parse_roles("") == []

    def test_parse_roles_valid(self, cog):
        assert cog._parse_roles("<@&123> <@&456>") == [123, 456]

    def test_parse_bonus_roles_empty(self, cog):
        assert cog._parse_bonus_roles(None) == {}

    def test_parse_bonus_roles_valid(self, cog):
        result = cog._parse_bonus_roles("<@&123>:5,<@&456>:10")
        assert result == {"123": 5, "456": 10}

    def test_parse_messages_none(self, cog):
        assert cog._parse_messages(None) is None

    def test_parse_messages_valid(self, cog):
        result = cog._parse_messages("100,<#789>")
        assert result == {"count": 100, "channel_id": 789}

    def test_parse_messages_invalid(self, cog):
        assert cog._parse_messages("invalid") is None
        assert cog._parse_messages("100") is None


class TestBuildEmbed:
    def test_build_embed_basic(self):
        from datetime import timedelta
        from bot.commands.giveaway import build_embed
        giveaway = {
            "prize": "Test Prize",
            "host_id": 123,
            "donor_id": None,
            "winners_count": 1,
            "ends_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "extra_text": None,
            "image_url": None,
        }
        embed = build_embed(giveaway, 0)
        assert embed.title == "🎉 GIVEAWAY 🎉"
        assert "Test Prize" in embed.description

    def test_build_embed_with_extras(self):
        from datetime import timedelta
        from bot.commands.giveaway import build_embed
        giveaway = {
            "prize": "Prize",
            "host_id": 123,
            "donor_id": 456,
            "winners_count": 3,
            "ends_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "extra_text": "Extra info",
            "image_url": "https://example.com/img.png",
        }
        embed = build_embed(giveaway, 10)
        field_values = [f.value for f in embed.fields]
        assert "<@456>" in str(field_values)
        assert "Extra info" in str(field_values)

    def test_build_embed_ended(self):
        from datetime import timedelta
        from bot.commands.giveaway import build_embed
        now = datetime.now(timezone.utc)
        giveaway = {
            "prize": "Prize",
            "host_id": 123,
            "donor_id": None,
            "winners_count": 1,
            "ends_at": now - timedelta(hours=1),
            "ended_at": now,
            "extra_text": None,
            "image_url": None,
        }
        embed = build_embed(giveaway, 5, ended=True)
        assert "ENDED" in embed.title


class TestGiveawayCommandsCheckAdmin:
    @pytest.mark.asyncio
    async def test_check_admin_success(self, cog):
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.user = MagicMock(id=2)
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        assert await cog._check_admin(interaction, "test") is True

    @pytest.mark.asyncio
    async def test_check_admin_failure(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.user = MagicMock(id=2)
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        assert await cog._check_admin(interaction, "test") is False
        interaction.followup.send.assert_called()


class TestGiveawayCommandsGstart:
    @pytest.mark.asyncio
    async def test_gstart_invalid_duration(self, cog):
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.user = MagicMock(id=2)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await cog.gstart.callback(cog, interaction, "invalid", 1, "Prize")
        assert "Invalid duration" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_duration_too_short(self, cog):
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.user = MagicMock(id=2)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await cog.gstart.callback(cog, interaction, "30s", 1, "Prize")
        assert "Invalid duration" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_invalid_winners(self, cog):
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.user = MagicMock(id=2)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await cog.gstart.callback(cog, interaction, "1h", 0, "Prize")
        assert "Winners" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_prize_too_long(self, cog):
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.user = MagicMock(id=2)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await cog.gstart.callback(cog, interaction, "1h", 1, "X" * 600)
        assert "Prize max" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.user = MagicMock(id=2)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await cog.gstart.callback(cog, interaction, "1h", 1, "Prize")
        assert "Admin" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_gstart_success(self, cog):
        conn = MagicMock()
        conn.execute = AsyncMock()
        cog.bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.channel_id = 2
        interaction.user = MagicMock(id=3)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        msg = MagicMock(id=999)
        interaction.followup.send = AsyncMock(return_value=msg)
        await cog.gstart.callback(cog, interaction, "1h", 1, "Prize")
        interaction.followup.send.assert_called()

    @pytest.mark.asyncio
    async def test_gstart_error(self, cog, caplog):
        conn = MagicMock()
        conn.execute = AsyncMock(side_effect=Exception("DB error"))
        cog.bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.channel_id = 2
        interaction.user = MagicMock(id=3)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await cog.gstart.callback(cog, interaction, "1h", 1, "Prize")
        assert "Error starting" in str(interaction.followup.send.call_args)


class TestGiveawayView:
    @pytest.fixture
    def view(self, mock_bot):
        return GiveawayView(uuid.uuid4(), mock_bot)

    @pytest.mark.asyncio
    async def test_get_giveaway(self, view, mock_bot):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": view.giveaway_id})
        mock_bot.db_pool = make_db_ctx(conn)
        result = await view._get_giveaway(123)
        assert result is not None

    @pytest.mark.asyncio
    async def test_check_eligibility_bypass(self, view):
        interaction = MagicMock()
        role = MagicMock(id=999)
        interaction.user = MagicMock(roles=[role])
        giveaway = {"bypass_roles": [999], "required_roles": [], "blacklist_roles": []}
        ok, reason = await view._check_eligibility(interaction, giveaway)
        assert ok is True

    @pytest.mark.asyncio
    async def test_check_eligibility_blacklisted(self, view):
        interaction = MagicMock()
        role = MagicMock(id=888)
        interaction.user = MagicMock(roles=[role])
        giveaway = {"bypass_roles": [], "required_roles": [], "blacklist_roles": [888]}
        ok, reason = await view._check_eligibility(interaction, giveaway)
        assert ok is False
        assert "blacklisted" in reason

    @pytest.mark.asyncio
    async def test_check_eligibility_missing_required(self, view):
        interaction = MagicMock()
        interaction.user = MagicMock(roles=[])
        giveaway = {"bypass_roles": [], "required_roles": [777], "blacklist_roles": []}
        ok, reason = await view._check_eligibility(interaction, giveaway)
        assert ok is False

    @pytest.mark.asyncio
    async def test_check_eligibility_donor_blocked(self, view):
        interaction = MagicMock()
        interaction.user = MagicMock(id=123, roles=[])
        giveaway = {
            "bypass_roles": [],
            "required_roles": [],
            "blacklist_roles": [],
            "no_donor_win": True,
            "donor_id": 123,
        }
        ok, reason = await view._check_eligibility(interaction, giveaway)
        assert ok is False

    def test_calculate_entries_base(self, view):
        roles = []
        giveaway = {"bonus_roles": {}}
        entries = view._calculate_entries(roles, giveaway)
        assert entries == 1

    def test_calculate_entries_with_bonus(self, view):
        role = MagicMock(id=100)
        roles = [role]
        giveaway = {"bonus_roles": {"100": 5}}
        entries = view._calculate_entries(roles, giveaway)
        assert entries == 6

    @pytest.mark.asyncio
    async def test_add_entry_success(self, view, mock_bot):
        conn = MagicMock()
        conn.execute = AsyncMock()
        mock_bot.db_pool = make_db_ctx(conn)
        result = await view._add_entry(uuid.uuid4(), 123, 1)
        assert result is True

    @pytest.mark.asyncio
    async def test_add_entry_duplicate(self, view, mock_bot):
        conn = MagicMock()
        conn.execute = AsyncMock(side_effect=Exception("unique"))
        mock_bot.db_pool = make_db_ctx(conn)
        result = await view._add_entry(uuid.uuid4(), 123, 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_update_embed(self, view, mock_bot):
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=10)
        conn.fetchrow = AsyncMock(return_value={
            "prize": "Test",
            "host_id": 1,
            "donor_id": None,
            "winners_count": 1,
            "ends_at": datetime.now(timezone.utc),
            "extra_text": None,
            "image_url": None,
        })
        mock_bot.db_pool = make_db_ctx(conn)
        message = MagicMock()
        message.edit = AsyncMock()
        await view._update_embed(message, view.giveaway_id)
        message.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_embed_no_giveaway(self, view, mock_bot):
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchrow = AsyncMock(return_value=None)
        mock_bot.db_pool = make_db_ctx(conn)
        message = MagicMock()
        message.edit = AsyncMock()
        await view._update_embed(message, view.giveaway_id)
        message.edit.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_button_giveaway_not_found(self, view, mock_bot):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=None)
        mock_bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        interaction.message = MagicMock(id=123)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await view.join_button.callback(interaction)
        assert "not found" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_ended(self, view, mock_bot):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"is_active": False})
        mock_bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        interaction.message = MagicMock(id=123)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await view.join_button.callback(interaction)
        assert "ended" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_not_eligible(self, view, mock_bot):
        giveaway = {
            "id": view.giveaway_id,
            "is_active": True,
            "bypass_roles": [],
            "required_roles": [],
            "blacklist_roles": [111],
        }
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=giveaway)
        mock_bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        interaction.message = MagicMock(id=123)
        role = MagicMock(id=111)
        interaction.user = MagicMock(roles=[role])
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await view.join_button.callback(interaction)
        assert "blacklisted" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_already_joined(self, view, mock_bot):
        from datetime import timedelta
        giveaway = {
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
        }
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=giveaway)
        conn.execute = AsyncMock(side_effect=Exception("dup"))
        mock_bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        interaction.message = MagicMock(id=123)
        interaction.user = MagicMock(id=999, roles=[])
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await view.join_button.callback(interaction)
        assert "already" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_success(self, view, mock_bot):
        from datetime import timedelta
        giveaway = {
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
        }
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=giveaway)
        conn.execute = AsyncMock()
        conn.fetchval = AsyncMock(return_value=1)
        mock_bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        message = MagicMock()
        message.edit = AsyncMock()
        interaction.message = message
        interaction.user = MagicMock(id=999, roles=[])
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await view.join_button.callback(interaction)
        assert "joined" in str(interaction.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_join_button_error(self, view, mock_bot, caplog):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(side_effect=Exception("DB error"))
        mock_bot.db_pool = make_db_ctx(conn)
        interaction = MagicMock()
        interaction.message = MagicMock(id=123)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        await view.join_button.callback(interaction)
        assert "Error" in str(interaction.followup.send.call_args)


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.giveaway import setup
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
