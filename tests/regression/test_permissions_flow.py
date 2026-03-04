from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.server_roles import set_server_role
from config.constants import Role

_BOT = Path(__file__).parents[2] / "bot" / "commands"


def test_permissions_add_uses_select_then_insert():
    text = (_BOT / "permissions.py").read_text()
    assert "INSERT INTO user_permissions" in text and "ON CONFLICT" not in text
    assert "SELECT" in text and "fetchval" in text


def test_reaction_roles_add_uses_select_then_insert():
    text = (_BOT / "reaction_roles.py").read_text()
    assert "INSERT INTO reaction_roles" in text and "ON CONFLICT" not in text
    assert "fetchval" in text or "SELECT" in text


@pytest.mark.asyncio
async def test_set_server_role_upserts_when_server_missing():
    conn = MagicMock()
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock(acquire=acquire)
    assert await set_server_role(pool, 123, Role.MODERATOR, 999, server_name="Test") is True
    call_str = str(conn.execute.call_args)
    assert "INSERT" in call_str and "ON CONFLICT" in call_str
    assert "999" in call_str or "moderator_role_id" in call_str
