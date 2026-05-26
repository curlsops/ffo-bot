from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.faq import FAQCommands, _invalidate_faq_cache
from tests.helpers import assert_followup_contains, build_faq_bot, mock_db_ctx, mock_interaction


@pytest.fixture
def cog():
    return FAQCommands(build_faq_bot())


def test_invalidate_faq_cache_no_cache():
    _invalidate_faq_cache(None, 1, None)


def test_invalidate_faq_cache_with_topic():
    c = MagicMock()
    _invalidate_faq_cache(c, 7, "rules")
    assert c.delete.call_count >= 3


def test_invalidate_faq_cache_without_topic_skips_entry_key():
    c = MagicMock()
    _invalidate_faq_cache(c, 7, None)
    assert c.delete.call_count == 2


@pytest.mark.asyncio
async def test_list_all_populates_cache_when_rows_from_db(cog):
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = None
    conn = AsyncMock(
        fetch=AsyncMock(
            return_value=[{"topic": "a", "question": "q", "answer": "z"}],
        )
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.list_cmd.callback(cog.faq_group, i, None)
    cog.bot.cache.set.assert_called()


@pytest.mark.asyncio
async def test_submit_no_guild(cog):
    i = mock_interaction()
    i.guild_id = None
    await cog.faq_group.submit_cmd.callback(cog.faq_group, i, "Hello")
    cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_submit_success_without_notifier(cog):
    cog.bot.settings = MagicMock(feature_faq_submissions=True)
    cog.bot.notifier = None
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value={"id": "550e8400-e29b-41d4-a716-446655440000"})
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.submit_cmd.callback(cog.faq_group, i, "Question text")
    i.followup.send.assert_awaited_once_with(
        "Question submitted! Admins will review it and may add it to the FAQ.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_edit_not_admin(cog):
    with patch("bot.commands.faq.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.faq_group.edit_cmd.callback(cog.faq_group, i, "rules", "q", None)
        cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_edit_with_notifier(cog):
    cog.bot.notifier = MagicMock()
    cog.bot.notifier.notify_faq_changed = AsyncMock()
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value={"question": "a", "answer": "b"}),
        execute=AsyncMock(),
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.edit_cmd.callback(cog.faq_group, i, "rules", "nq", None)
    cog.bot.notifier.notify_faq_changed.assert_awaited()


@pytest.mark.asyncio
async def test_submissions_not_admin(cog):
    with patch("bot.commands.faq.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.faq_group.submissions_cmd.callback(cog.faq_group, i)
        cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_delete_empty_topic(cog):
    i = mock_interaction()
    await cog.faq_group.delete_cmd.callback(cog.faq_group, i, "   ")
    assert_followup_contains(i, "Topic is required")


@pytest.mark.asyncio
async def test_delete_not_admin(cog):
    with patch("bot.commands.faq.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.faq_group.delete_cmd.callback(cog.faq_group, i, "rules")
        cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_delete_success_notifies(cog):
    cog.bot.notifier = MagicMock()
    cog.bot.notifier.notify_faq_changed = AsyncMock()
    conn = AsyncMock(execute=AsyncMock(return_value="DELETE 1"))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.delete_cmd.callback(cog.faq_group, i, "rules")
    cog.bot.notifier.notify_faq_changed.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_topic_cache_hit(cog):
    row = {"question": "Q?", "answer": "A!"}
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = dict(row)
    i = mock_interaction()
    await cog.faq_group.list_cmd.callback(cog.faq_group, i, "RULES")
    cog.bot.db_pool.acquire.assert_not_called()
    assert i.followup.send.call_args[1]["embed"].title == "Q?"


@pytest.mark.asyncio
async def test_list_topic_fetch_then_cache(cog):
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = None
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value={"question": "QQ", "answer": "AA"}),
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.list_cmd.callback(cog.faq_group, i, "rules")
    cog.bot.cache.set.assert_called()


@pytest.mark.asyncio
async def test_list_topic_no_row(cog):
    cog.bot.cache = None
    conn = AsyncMock(fetchrow=AsyncMock(return_value=None))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.list_cmd.callback(cog.faq_group, i, "none")
    assert_followup_contains(i, "No FAQ entry")


@pytest.mark.asyncio
async def test_list_all_cache_hit(cog):
    rows = [{"topic": "a", "question": "q", "answer": "z"}]
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = rows
    i = mock_interaction()
    await cog.faq_group.list_cmd.callback(cog.faq_group, i, None)
    cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_list_all_fetch_exception(cog):
    cog.bot.cache = None
    conn = AsyncMock(fetch=AsyncMock(side_effect=RuntimeError("db")))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.faq.send_error", new_callable=AsyncMock) as se:
        await cog.faq_group.list_cmd.callback(cog.faq_group, i, None)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_submit_disabled(cog):
    cog.bot.settings.feature_faq_submissions = False
    i = mock_interaction()
    await cog.faq_group.submit_cmd.callback(cog.faq_group, i, "Why?")
    assert_followup_contains(i, "disabled")


@pytest.mark.asyncio
async def test_submit_empty_question(cog):
    cog.bot.settings.feature_faq_submissions = True
    i = mock_interaction()
    await cog.faq_group.submit_cmd.callback(cog.faq_group, i, "   ")
    assert_followup_contains(i, "empty")


@pytest.mark.asyncio
async def test_submit_with_notifier(cog):
    cog.bot.settings.feature_faq_submissions = True
    cog.bot.notifier = MagicMock()
    cog.bot.notifier.notify_faq_submission = AsyncMock()
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value={"id": "550e8400-e29b-41d4-a716-446655440000"})
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.submit_cmd.callback(cog.faq_group, i, "Question text")
    cog.bot.notifier.notify_faq_submission.assert_awaited()


@pytest.mark.asyncio
async def test_submit_exception(cog):
    cog.bot.settings.feature_faq_submissions = True
    conn = AsyncMock(fetchrow=AsyncMock(side_effect=RuntimeError("x")))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.faq.send_error", new_callable=AsyncMock) as se:
        await cog.faq_group.submit_cmd.callback(cog.faq_group, i, "Q")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_add_not_admin(cog):
    with patch("bot.commands.faq.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.faq_group.add_cmd.callback(cog.faq_group, i, "t", "q", "a")
        cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_add_exception(cog):
    conn = AsyncMock(
        fetchval=AsyncMock(return_value=0), execute=AsyncMock(side_effect=RuntimeError("db"))
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.faq.send_error", new_callable=AsyncMock) as se:
        await cog.faq_group.add_cmd.callback(cog.faq_group, i, "nt", "q", "a")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_add_with_notifier(cog):
    cog.bot.notifier = MagicMock()
    cog.bot.notifier.notify_faq_changed = AsyncMock()
    conn = AsyncMock(fetchval=AsyncMock(return_value=1), execute=AsyncMock())
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.add_cmd.callback(cog.faq_group, i, "nt", "q", "a")
    cog.bot.notifier.notify_faq_changed.assert_awaited()


@pytest.mark.asyncio
async def test_edit_empty_topic(cog):
    i = mock_interaction()
    await cog.faq_group.edit_cmd.callback(cog.faq_group, i, "  ", "x", None)
    assert_followup_contains(i, "Topic is required")


@pytest.mark.asyncio
async def test_edit_exception(cog):
    conn = AsyncMock(
        fetchrow=AsyncMock(return_value={"question": "a", "answer": "b"}),
        execute=AsyncMock(side_effect=RuntimeError("x")),
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.faq.send_error", new_callable=AsyncMock) as se:
        await cog.faq_group.edit_cmd.callback(cog.faq_group, i, "rules", "nq", None)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_submissions_empty(cog):
    conn = AsyncMock(fetch=AsyncMock(return_value=[]))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.submissions_cmd.callback(cog.faq_group, i)
    assert_followup_contains(i, "No pending")


@pytest.mark.asyncio
async def test_submissions_with_rows(cog):
    rows = [
        {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "question": "x" * 70,
            "submitter_id": 9,
            "created_at": None,
        }
    ]
    conn = AsyncMock(fetch=AsyncMock(return_value=rows))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.submissions_cmd.callback(cog.faq_group, i)
    assert "Pending" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_submissions_exception(cog):
    conn = AsyncMock(fetch=AsyncMock(side_effect=RuntimeError("db")))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.faq_group.submissions_cmd.callback(cog.faq_group, i)
    assert "Error" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_delete_exception(cog):
    conn = AsyncMock(execute=AsyncMock(side_effect=RuntimeError("db")))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.faq.send_error", new_callable=AsyncMock) as se:
        await cog.faq_group.delete_cmd.callback(cog.faq_group, i, "rules")
    se.assert_awaited()


@pytest.mark.asyncio
async def test_faq_cog_lifecycle():
    bot = build_faq_bot()
    bot.tree.add_command = MagicMock()
    bot.tree.remove_command = MagicMock()
    c = FAQCommands(bot)
    await c.cog_load()
    bot.tree.add_command.assert_called_once()
    await c.cog_unload()
    bot.tree.remove_command.assert_called_once_with("faq")
    from bot.commands import faq as faq_mod

    bot.add_cog = AsyncMock()
    await faq_mod.setup(bot)
    bot.add_cog.assert_awaited_once()
