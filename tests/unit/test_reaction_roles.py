from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.reaction_roles import ReactionRoleCommands, _parse_message_ref


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


def _interaction(guild_id=1, channel_id=2, user_id=3):
    i = MagicMock()
    i.guild_id = guild_id
    i.channel_id = channel_id
    i.channel = MagicMock(id=channel_id)
    i.user = MagicMock(id=user_id)
    i.guild = MagicMock(id=guild_id)
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


class TestParseMessageRef:
    def test_message_link(self):
        assert _parse_message_ref("https://discord.com/channels/111/222/333", 1, 99) == (222, 333)

    def test_raw_id(self):
        assert _parse_message_ref("123456789", 1, 99) == (99, 123456789)

    def test_invalid(self):
        assert _parse_message_ref("abc", 1, 99) is None
        assert _parse_message_ref("", 1, 99) is None


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.db_pool = _db_ctx(AsyncMock())
    return bot


@pytest.fixture
def cog(mock_bot):
    return ReactionRoleCommands(mock_bot)


class TestReactionRoleCommands:
    @pytest.mark.asyncio
    async def test_add_invalid_message(self, cog):
        i = _interaction()
        await cog.reactionrole_add.callback(cog, i, "invalid", "👍", MagicMock(id=123))
        assert "Invalid message" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_add_success(self, cog):
        msg = MagicMock(add_reaction=AsyncMock())
        channel = MagicMock(fetch_message=AsyncMock(return_value=msg))
        cog.bot.get_channel = MagicMock(return_value=channel)
        role = MagicMock(id=456, mention="<@&456>")
        i = _interaction()
        await cog.reactionrole_add.callback(
            cog, i, "https://discord.com/channels/1/2/123", "👍", role
        )
        msg.add_reaction.assert_awaited_with("👍")
        i.followup.send.assert_called()

    @pytest.mark.asyncio
    async def test_remove_not_found(self, cog):
        conn = AsyncMock(execute=AsyncMock(return_value="UPDATE 0"))
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.reactionrole_remove.callback(cog, i, "https://discord.com/channels/1/2/123", "👍")
        assert "not found" in str(i.followup.send.call_args).lower()

    @pytest.mark.asyncio
    async def test_list_empty(self, cog):
        conn = AsyncMock(fetch=AsyncMock(return_value=[]))
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.reactionrole_list.callback(cog, i)
        assert "No reaction roles" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_list_with_rows(self, cog):
        conn = AsyncMock(
            fetch=AsyncMock(
                return_value=[{"message_id": 1, "channel_id": 2, "emoji": "👍", "role_id": 99}]
            )
        )
        cog.bot.db_pool = _db_ctx(conn)
        i = _interaction()
        await cog.reactionrole_list.callback(cog, i)
        assert "Reaction Roles" in str(i.followup.send.call_args)

    @pytest.mark.asyncio
    async def test_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = _interaction()
        await cog.reactionrole_list.callback(cog, i)
        assert "Admin" in str(i.followup.send.call_args)


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.reaction_roles import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
