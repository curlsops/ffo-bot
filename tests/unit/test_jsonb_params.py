import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.auth.permissions import PermissionChecker, PermissionContext
from bot.commands.giveaway import GiveawayCommands
from bot.utils.notifier import AdminNotifier
from config.constants import Role


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.fixture
def bot_with_conn():
    bot = MagicMock()
    conn = AsyncMock()
    bot.db_pool.acquire.return_value = _db_ctx(conn)
    return bot, conn


class TestNotifierJsonbParams:
    @pytest.mark.asyncio
    async def test_set_notify_channel_passes_json_string(self, bot_with_conn):
        bot, conn = bot_with_conn
        await AdminNotifier(bot).set_notify_channel(999, 123456789)
        conn.execute.assert_awaited_once()
        param = conn.execute.call_args[0][1]
        assert isinstance(param, str) and json.loads(param) == {"notify_channel_id": 123456789}


class TestGiveawayJsonbParams:
    @pytest.mark.asyncio
    async def test_gstart_passes_native_types(self, bot_with_conn):
        bot, conn = bot_with_conn
        bot.permission_checker.check_role = AsyncMock(return_value=True)
        bot.metrics = bot.notifier = None
        cog = GiveawayCommands(bot)

        i = MagicMock(guild_id=1, channel_id=2, user=MagicMock(id=3))
        i.response.defer = AsyncMock()
        i.followup.send = AsyncMock(return_value=MagicMock(id=999))

        await cog.gstart.callback(
            cog,
            i,
            "1h",
            1,
            "Prize",
            donor=None,
            required_roles=None,
            blacklist_roles=None,
            bypass_roles=None,
            bonus_roles=None,
            messages=None,
            nodonorwin=False,
            nodefaults=False,
            ping=False,
            extra_text=None,
            image=None,
        )

        insert = next(
            c for c in conn.execute.call_args_list if "INSERT INTO giveaways" in str(c[0])
        )
        args = insert[0][1:]
        assert isinstance(args[8], list) and isinstance(args[9], list)
        assert isinstance(args[10], list) and isinstance(args[11], dict)
        assert args[12] is None


class TestAuditLogJsonbParams:
    @pytest.mark.asyncio
    async def test_log_permission_denial_passes_json_string(self):
        conn = MagicMock(execute=AsyncMock())

        @asynccontextmanager
        async def acquire():
            yield conn

        db_pool = MagicMock(acquire=MagicMock(return_value=acquire()))
        ctx = PermissionContext(server_id=1, user_id=2, command_name="test_cmd")
        await PermissionChecker(db_pool, MagicMock())._log_permission_denial(ctx, Role.SUPER_ADMIN)

        conn.execute.assert_awaited_once()
        param = conn.execute.call_args[0][3]
        assert isinstance(param, str) and json.loads(param) == {
            "command": "test_cmd",
            "required_role": "super_admin",
        }


class TestDatabasePoolJsonbCodec:
    @pytest.mark.asyncio
    async def test_create_pool_registers_init(self):
        with patch("database.connection.asyncpg.create_pool", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock()
            from database.connection import DatabasePool

            await DatabasePool.create("postgresql://localhost/test", min_size=1, max_size=2)
            assert mock.call_args[1].get("init").__name__ == "_init_connection"
