from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.commands.quotebook import QuotebookCommands


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.cache = None
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.db_pool.acquire = MagicMock()
    return bot


@pytest.fixture
def cog(mock_bot):
    return QuotebookCommands(mock_bot)


def _interaction(guild_id=1, channel_id=2, user_id=3, display_name="TestUser"):
    i = MagicMock(guild_id=guild_id, channel_id=channel_id)
    i.user = MagicMock(id=user_id, display_name=display_name, roles=[])
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestQuoteSubmit:
    @pytest.mark.asyncio
    async def test_submit_success(self, cog):
        conn = AsyncMock(execute=AsyncMock())
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_submit.callback(cog, i, "Hello world", None)
        conn.execute.assert_awaited_once()
        i.followup.send.assert_awaited_with(
            "Quote submitted! An admin will review it.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_submit_with_attribution(self, cog):
        conn = AsyncMock(execute=AsyncMock())
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_submit.callback(cog, i, "Quote text", "— Einstein")
        call = conn.execute.call_args
        assert "Einstein" in str(call)

    @pytest.mark.asyncio
    async def test_submit_empty_rejected(self, cog):
        i = _interaction()
        await cog.quote_submit.callback(cog, i, "   ", None)
        i.followup.send.assert_awaited_with("Quote cannot be empty.", ephemeral=True)
        cog.bot.db_pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_truncates_long_text(self, cog):
        conn = AsyncMock(execute=AsyncMock())
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        long_text = "A" * 600
        await cog.quote_submit.callback(cog, i, long_text, None)
        call = conn.execute.call_args
        assert len(call[0][2]) <= 500


class TestQuoteList:
    @pytest.mark.asyncio
    async def test_list_empty(self, cog):
        conn = AsyncMock(fetch=AsyncMock(return_value=[]))
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_list.callback(cog, i)
        i.followup.send.assert_awaited_with("No pending quotes.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_list_shows_pending(self, cog):
        conn = AsyncMock(
            fetch=AsyncMock(
                return_value=[
                    {
                        "id": "a1b2c3d4-0000-0000-0000-000000000001",
                        "quote_text": "Test quote",
                        "submitter_id": 123,
                        "attribution": "— Someone",
                        "created_at": None,
                    }
                ]
            )
        )
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_list.callback(cog, i)
        call_args = i.followup.send.call_args
        assert "Pending quotes" in call_args[0][0]
        assert "Test quote" in call_args[0][0]


class TestQuoteApprove:
    @pytest.mark.asyncio
    async def test_approve_success(self, cog):
        conn = AsyncMock(execute=AsyncMock(return_value="UPDATE 1"))
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_approve.callback(cog, i, "a1b2c3d4-0000-0000-0000-000000000001")
        i.followup.send.assert_awaited_with("Quote approved!", ephemeral=True)

    @pytest.mark.asyncio
    async def test_approve_invalid_id(self, cog):
        i = _interaction()
        await cog.quote_approve.callback(cog, i, "not-a-uuid")
        i.followup.send.assert_awaited_with("Invalid quote ID.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_approve_not_found(self, cog):
        conn = AsyncMock(execute=AsyncMock(return_value="UPDATE 0"))
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_approve.callback(cog, i, "a1b2c3d4-0000-0000-0000-000000000001")
        i.followup.send.assert_awaited_with("Quote not found or already approved.", ephemeral=True)


class TestQuoteDelete:
    @pytest.mark.asyncio
    async def test_delete_success(self, cog):
        conn = AsyncMock(execute=AsyncMock())
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_delete.callback(cog, i, "a1b2c3d4-0000-0000-0000-000000000001")
        i.followup.send.assert_awaited_with("Quote deleted.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_delete_invalid_id(self, cog):
        i = _interaction()
        await cog.quote_delete.callback(cog, i, "bad-id")
        i.followup.send.assert_awaited_with("Invalid quote ID.", ephemeral=True)


class TestQuoteSubmitVariants:
    @pytest.mark.parametrize("text", ["Short", "A" * 100, "Unicode: 日本語"])
    @pytest.mark.asyncio
    async def test_submit_various_text(self, cog, text):
        conn = AsyncMock(execute=AsyncMock())
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_submit.callback(cog, i, text, None)
        conn.execute.assert_awaited_once()


class TestQuoteRandom:
    @pytest.mark.asyncio
    async def test_random_empty(self, cog):
        conn = AsyncMock(fetch=AsyncMock(return_value=[]))
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_random.callback(cog, i)
        i.followup.send.assert_awaited_with("No quotes in the book yet.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_random_returns_quote(self, cog):
        conn = AsyncMock(
            fetch=AsyncMock(return_value=[{"quote_text": "Wise words", "attribution": "— Sage"}])
        )
        cog.bot.db_pool.acquire.return_value = _db_ctx(conn)
        i = _interaction()
        await cog.quote_random.callback(cog, i)
        call_args = i.followup.send.call_args
        embed = call_args[1].get("embed")
        assert embed is not None
        assert "Wise words" in embed.description
        assert "Sage" in embed.description
