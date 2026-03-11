from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.reaction_roles import ReactionRoleCommands, _parse_message_ref
from tests.helpers import assert_followup_contains, invoke, mock_db_pool, mock_interaction


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
    bot.cache = None
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    pool, _ = mock_db_pool()
    bot.db_pool = pool
    return bot


@pytest.fixture
def cog(mock_bot):
    return ReactionRoleCommands(mock_bot)


class TestReactionRoleCommands:
    @pytest.mark.asyncio
    async def test_add_invalid_message(self, cog):
        i = mock_interaction()
        await invoke(
            cog,
            "reactionrole_group",
            "add_cmd",
            i,
            message="invalid",
            emoji="👍",
            role=MagicMock(id=123),
        )
        assert_followup_contains(i, "Invalid message")

    @pytest.mark.asyncio
    async def test_add_success(self, cog):
        msg = MagicMock(add_reaction=AsyncMock())
        channel = MagicMock(fetch_message=AsyncMock(return_value=msg))
        cog.bot.get_channel = MagicMock(return_value=channel)
        role = MagicMock(id=456, mention="<@&456>")
        i = mock_interaction()
        await invoke(
            cog,
            "reactionrole_group",
            "add_cmd",
            i,
            message="https://discord.com/channels/1/2/123",
            emoji="👍",
            role=role,
        )
        msg.add_reaction.assert_awaited_with("👍")
        i.followup.send.assert_called()

    @pytest.mark.asyncio
    async def test_remove_not_found(self, cog):
        pool, _ = mock_db_pool(execute="UPDATE 0")
        cog.bot.db_pool = pool
        i = mock_interaction()
        await invoke(
            cog,
            "reactionrole_group",
            "remove_cmd",
            i,
            message="https://discord.com/channels/1/2/123",
            emoji="👍",
        )
        assert_followup_contains(i, "not found", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_list_empty(self, cog):
        pool, _ = mock_db_pool(fetch=[])
        cog.bot.db_pool = pool
        i = mock_interaction()
        await invoke(cog, "reactionrole_group", "list_cmd", i)
        assert_followup_contains(i, "No reaction roles")

    @pytest.mark.asyncio
    async def test_list_with_rows(self, cog):
        pool, _ = mock_db_pool(
            fetch=[{"message_id": 1, "channel_id": 2, "emoji": "👍", "role_id": 99}]
        )
        cog.bot.db_pool = pool
        i = mock_interaction()
        await invoke(cog, "reactionrole_group", "list_cmd", i)
        assert_followup_contains(i, "Reaction Roles")

    @pytest.mark.asyncio
    async def test_not_admin(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i = mock_interaction()
        await invoke(cog, "reactionrole_group", "list_cmd", i)
        assert_followup_contains(i, "Admin")


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup(self, mock_bot):
        from bot.commands.reaction_roles import setup

        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
