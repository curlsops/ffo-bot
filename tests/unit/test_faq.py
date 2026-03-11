from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.faq import FAQCommands
from tests.helpers import assert_followup_contains, mock_db_ctx, mock_interaction


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.cache = None
    bot.notifier = None
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.db_pool.acquire = MagicMock()
    return bot


@pytest.fixture
def cog(mock_bot):
    return FAQCommands(mock_bot)


class TestFaqListEmpty:
    @pytest.mark.asyncio
    async def test_list_empty_no_guild(self, cog):
        i = mock_interaction()
        i.guild_id = None
        await cog.faq_group.list_cmd.callback(cog.faq_group, i, None)
        cog.bot.db_pool.acquire.assert_not_called()


class TestFaqList:
    @pytest.mark.asyncio
    async def test_list_empty(self, cog):
        conn = AsyncMock(fetch=AsyncMock(return_value=[]))
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.list_cmd.callback(cog.faq_group, i, None)
        assert_followup_contains(i, "No FAQ entries")

    @pytest.mark.asyncio
    async def test_list_with_topics(self, cog):
        conn = AsyncMock(
            fetch=AsyncMock(
                return_value=[
                    {"topic": "rules", "question": "Rules?", "answer": "Be nice."},
                    {"topic": "whitelist", "question": "Whitelist?", "answer": "Post IGN."},
                ]
            )
        )
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.list_cmd.callback(cog.faq_group, i, None)
        call_kw = i.followup.send.call_args[1]
        embed = call_kw.get("embed")
        view = call_kw.get("view")
        assert embed is not None
        assert "rules" in embed.description
        assert "whitelist" in embed.description
        assert view is not None


class TestFaqGet:
    @pytest.mark.asyncio
    async def test_get_topic_found(self, cog):
        conn = AsyncMock(
            fetchrow=AsyncMock(
                return_value={"question": "How do I get whitelisted?", "answer": "Post your IGN."}
            )
        )
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.list_cmd.callback(cog.faq_group, i, "whitelist")
        embed = i.followup.send.call_args[1].get("embed")
        assert embed is not None
        assert "How do I get whitelisted?" in embed.title
        assert "Post your IGN" in embed.description

    @pytest.mark.asyncio
    async def test_get_topic_not_found(self, cog):
        conn = AsyncMock(fetchrow=AsyncMock(return_value=None))
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.list_cmd.callback(cog.faq_group, i, "nonexistent")
        assert_followup_contains(i, "No FAQ entry")


class TestFaqAdd:
    @pytest.mark.asyncio
    async def test_add_success(self, cog):
        conn = AsyncMock(fetchval=AsyncMock(return_value=0), execute=AsyncMock())
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.add_cmd.callback(
            cog.faq_group, i, "rules", "What are the rules?", "Be nice."
        )
        conn.execute.assert_awaited_once()
        assert_followup_contains(i, "added/updated")

    @pytest.mark.asyncio
    async def test_add_max_topics(self, cog):
        conn = AsyncMock(fetchval=AsyncMock(return_value=25))
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.add_cmd.callback(cog.faq_group, i, "new", "Q?", "A.")
        assert_followup_contains(i, "Maximum")
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_empty_fields_rejected(self, cog):
        i = mock_interaction()
        await cog.faq_group.add_cmd.callback(cog.faq_group, i, "  ", "Q", "A")
        assert_followup_contains(i, "required", case_sensitive=False)
        cog.bot.db_pool.acquire.assert_not_called()


class TestFaqEdit:
    @pytest.mark.asyncio
    async def test_edit_success(self, cog):
        conn = AsyncMock(
            fetchrow=AsyncMock(return_value={"question": "Old Q", "answer": "Old A"}),
            execute=AsyncMock(),
        )
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.edit_cmd.callback(cog.faq_group, i, "rules", "New Q", None)
        assert_followup_contains(i, "updated")

    @pytest.mark.asyncio
    async def test_edit_not_found(self, cog):
        conn = AsyncMock(fetchrow=AsyncMock(return_value=None))
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.edit_cmd.callback(cog.faq_group, i, "nonexistent", "Q", None)
        assert_followup_contains(i, "No FAQ entry")

    @pytest.mark.asyncio
    async def test_edit_no_changes_rejected(self, cog):
        i = mock_interaction()
        await cog.faq_group.edit_cmd.callback(cog.faq_group, i, "rules", None, None)
        assert_followup_contains(i, "question or answer", case_sensitive=False)


class TestFaqDelete:
    @pytest.mark.asyncio
    async def test_delete_success(self, cog):
        conn = AsyncMock(execute=AsyncMock(return_value="DELETE 1"))
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.delete_cmd.callback(cog.faq_group, i, "rules")
        assert_followup_contains(i, "deleted")

    @pytest.mark.asyncio
    async def test_delete_not_found(self, cog):
        conn = AsyncMock(execute=AsyncMock(return_value="DELETE 0"))
        cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
        i = mock_interaction()
        await cog.faq_group.delete_cmd.callback(cog.faq_group, i, "nonexistent")
        assert_followup_contains(i, "No FAQ entry")


class TestFaqAutocomplete:
    @pytest.mark.asyncio
    async def test_autocomplete_no_guild_returns_empty(self):
        from bot.commands.faq import _faq_topic_autocomplete

        i = MagicMock(guild_id=None)
        i.client = MagicMock()
        result = await _faq_topic_autocomplete(i, "")
        assert result == []

    @pytest.mark.asyncio
    async def test_autocomplete_returns_choices(self):
        from bot.commands.faq import _faq_topic_autocomplete

        bot = MagicMock()
        bot.cache = None
        conn = AsyncMock(fetch=AsyncMock(return_value=[{"topic": "rules"}, {"topic": "whitelist"}]))
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        bot.db_pool.acquire.return_value = ctx
        i = MagicMock(guild_id=1, client=bot)
        result = await _faq_topic_autocomplete(i, "")
        assert len(result) >= 1
        assert any(c.value == "rules" for c in result)
