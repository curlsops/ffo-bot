from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bot.utils.server_roles import set_server_role
from config.constants import Role
from tests.helpers import db_pool_with_conn, mock_db_conn

_BOT = Path(__file__).resolve().parents[2] / "bot" / "commands"


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
    conn = mock_db_conn()
    conn.execute = AsyncMock()
    pool = db_pool_with_conn(conn)
    assert await set_server_role(pool, 123, Role.MODERATOR, 999, server_name="Test") is True
    conn.execute.assert_awaited_once()
    sql, server_id, server_name, merge = conn.execute.call_args.args
    assert "INSERT INTO servers" in sql and "ON CONFLICT" in sql
    assert server_id == 123
    assert server_name == "Test"
    assert merge == {"moderator_role_id": 999}
