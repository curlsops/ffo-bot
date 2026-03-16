import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from bot.commands.giveaway import GiveawayCommands
from bot.views.giveaway import GiveawayView
from tests.helpers import db_pool_with_conn, mock_interaction

OP_START = app_commands.Choice(name="Start", value="start")
OP_REROLL = app_commands.Choice(name="Reroll", value="reroll")


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


def db_ctx(conn):
    return db_pool_with_conn(conn, exit_result=None)


def interaction(guild_id=1, channel_id=2, user_id=3, msg_id=123):
    return mock_interaction(
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        msg_id=msg_id,
        user_roles=[],
        followup_send_return=MagicMock(id=999),
    )


def giveaway(prize="Prize", host_id=123, donor_id=None, winners_count=1, hours=1, **kw):
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


def active_giveaway(current_view, **overrides):
    return {
        "id": current_view.giveaway_id,
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


def entries(count):
    return [{"user_id": index, "entries": 1} for index in range(count)]
