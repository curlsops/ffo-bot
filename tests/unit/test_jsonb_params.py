"""JSONB params must be JSON strings for asyncpg."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.auth.permissions import PermissionChecker, PermissionContext
from bot.utils.notifier import AdminNotifier
from config.constants import Role


def db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestNotifierJsonbParams:
    @pytest.mark.asyncio
    async def test_set_notify_channel_passes_json_string_not_dict(self):
        bot = MagicMock()
        conn = AsyncMock()
        bot.db_pool.acquire.return_value = db_ctx(conn)
        notifier = AdminNotifier(bot)

        await notifier.set_notify_channel(999, 123456789)

        conn.execute.assert_awaited_once()
        config_param = conn.execute.call_args[0][1]
        assert isinstance(config_param, str), "JSONB param must be JSON string, not dict"
        assert json.loads(config_param) == {"notify_channel_id": 123456789}


class TestGiveawayJsonbParams:
    @pytest.mark.asyncio
    async def test_gstart_passes_json_strings_for_jsonb_columns(self):
        from bot.commands.giveaway import GiveawayCommands

        bot = MagicMock()
        bot.permission_checker.check_role = AsyncMock(return_value=True)
        bot.metrics = None
        bot.notifier = None
        conn = AsyncMock()
        bot.db_pool.acquire.return_value = db_ctx(conn)
        cog = GiveawayCommands(bot)

        interaction = MagicMock()
        interaction.guild_id = 1
        interaction.channel_id = 2
        interaction.user = MagicMock(id=3)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        msg = MagicMock(id=999)
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock(return_value=msg)

        await cog.gstart.callback(
            cog,
            interaction,
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

        insert_calls = [c for c in conn.execute.call_args_list if "INSERT INTO giveaways" in str(c[0])]
        assert len(insert_calls) >= 1
        args = insert_calls[0][0][1:]
        required_roles, blacklist_roles, bypass_roles, bonus_roles, message_req = (
            args[8],
            args[9],
            args[10],
            args[11],
            args[12],
        )
        for name, val in [
            ("required_roles", required_roles),
            ("blacklist_roles", blacklist_roles),
            ("bypass_roles", bypass_roles),
            ("bonus_roles", bonus_roles),
        ]:
            assert isinstance(val, str), f"{name} must be JSON string, got {type(val).__name__}"
            json.loads(val)
        assert message_req is None or isinstance(message_req, str)


class TestAuditLogJsonbParams:
    @pytest.mark.asyncio
    async def test_log_permission_denial_passes_json_string_not_dict(self):
        conn = MagicMock()
        conn.execute = AsyncMock()

        @asynccontextmanager
        async def acquire():
            yield conn

        db_pool = MagicMock()
        db_pool.acquire.return_value = acquire()
        checker = PermissionChecker(db_pool, MagicMock())
        ctx = PermissionContext(server_id=1, user_id=2, command_name="test_cmd")

        await checker._log_permission_denial(ctx, Role.SUPER_ADMIN)

        conn.execute.assert_awaited_once()
        details_param = conn.execute.call_args[0][3]
        assert isinstance(details_param, str), "details must be JSON string, not dict"
        parsed = json.loads(details_param)
        assert parsed == {"command": "test_cmd", "required_role": "super_admin"}


class TestDatabasePoolJsonbCodec:
    """DatabasePool must register JSONB codec so asyncpg returns dict/list on read."""

    @pytest.mark.asyncio
    async def test_create_pool_passes_init(self):
        from unittest.mock import patch

        mock_pool = MagicMock()
        with patch("database.connection.asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_pool
            from database.connection import DatabasePool

            await DatabasePool.create("postgresql://localhost/test", min_size=1, max_size=2)

            mock_create.assert_awaited_once()
            call_kwargs = mock_create.call_args[1]
            assert "init" in call_kwargs
            assert call_kwargs["init"].__name__ == "_init_connection"
