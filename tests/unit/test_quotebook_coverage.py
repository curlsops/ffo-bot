from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import discord
import pytest

from bot.commands import quotebook as quotebook_mod
from bot.commands.quotebook import (
    QuotebookCommands,
    _fetch_quote_approve_ids,
    _fetch_quote_ids,
    _invalidate_quotebook_cache,
    _quote_id_approve_autocomplete,
    _quote_id_autocomplete,
    _rows_to_choices,
    _rows_to_choices_with_approved,
)
from tests.helpers import build_quotebook_bot, mock_db_ctx, mock_db_pool, mock_interaction


@pytest.fixture
def cog():
    return QuotebookCommands(build_quotebook_bot())


def test_invalidate_quotebook_no_cache():
    _invalidate_quotebook_cache(None, 1)


def test_invalidate_quotebook_with_cache():
    c = MagicMock()
    _invalidate_quotebook_cache(c, 3)
    assert c.delete.call_count >= 4


def test_rows_to_choices_filters_and_truncates():
    rows = [
        {"id": UUID(int=5), "quote_text": "hello world", "approved": False},
    ]
    out = _rows_to_choices_with_approved(rows, "")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_list_exception(cog):
    conn = AsyncMock(fetch=AsyncMock(side_effect=RuntimeError("db")))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.quotebook.send_error", new_callable=AsyncMock) as se:
        await cog.quote_group.list_cmd.callback(cog.quote_group, i)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_submit_exception(cog):
    conn = AsyncMock(fetchrow=AsyncMock(side_effect=RuntimeError("db")))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.quotebook.send_error", new_callable=AsyncMock) as se:
        await cog.quote_group.submit_cmd.callback(cog.quote_group, i, "text", None)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_submit_no_guild(cog):
    i = mock_interaction()
    i.guild_id = None
    await cog.quote_group.submit_cmd.callback(cog.quote_group, i, "x", None)


@pytest.mark.asyncio
async def test_submit_with_notifier(cog):
    cog.bot.notifier = MagicMock()
    cog.bot.notifier.notify_quotebook_submitted = AsyncMock()
    conn = AsyncMock(fetchrow=AsyncMock(return_value={"id": UUID(int=1)}))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.quote_group.submit_cmd.callback(cog.quote_group, i, "t", None)
    cog.bot.notifier.notify_quotebook_submitted.assert_awaited()


@pytest.mark.asyncio
async def test_approve_posts_to_channel(cog):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value={"quote_text": "Hello", "attribution": "Me"})
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)

    ch = MagicMock()
    ch.send = AsyncMock()

    with patch(
        "bot.commands.quotebook.get_quotebook_channel_id",
        AsyncMock(return_value=42),
    ):
        with patch(
            "bot.commands.quotebook.get_or_fetch_channel",
            AsyncMock(return_value=ch),
        ):
            i = mock_interaction()
            qid = "12345678-1234-5678-1234-567812345678"
            await cog.quote_group.approve_cmd.callback(cog.quote_group, i, qid)
    ch.send.assert_awaited()


@pytest.mark.asyncio
async def test_approve_channel_forbidden_logs(cog):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value={"quote_text": "Hello", "attribution": None})
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)

    ch = MagicMock()
    ch.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no"))

    with patch(
        "bot.commands.quotebook.get_quotebook_channel_id",
        AsyncMock(return_value=42),
    ):
        with patch(
            "bot.commands.quotebook.get_or_fetch_channel",
            AsyncMock(return_value=ch),
        ):
            i = mock_interaction()
            await cog.quote_group.approve_cmd.callback(
                cog.quote_group,
                i,
                "12345678-1234-5678-1234-567812345678",
            )


@pytest.mark.asyncio
async def test_approve_exception_outer(cog):
    cog.bot.db_pool.acquire = MagicMock(side_effect=RuntimeError("pool"))
    i = mock_interaction()
    with patch("bot.commands.quotebook.send_error", new_callable=AsyncMock) as se:
        await cog.quote_group.approve_cmd.callback(
            cog.quote_group,
            i,
            "12345678-1234-5678-1234-567812345678",
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_delete_exception(cog):
    conn = AsyncMock(execute=AsyncMock(side_effect=RuntimeError("db")))
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    with patch("bot.commands.quotebook.send_error", new_callable=AsyncMock) as se:
        await cog.quote_group.delete_cmd.callback(
            cog.quote_group,
            i,
            "12345678-1234-5678-1234-567812345678",
        )
    se.assert_awaited()


class _AsyncIter:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        self._it = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_import_quotes_from_channel(cog):
    msg = MagicMock()
    msg.author.bot = False
    msg.content = '"Quoted" - Someone'

    channel = MagicMock()
    channel.id = 99
    channel.mention = "#src"
    channel.history = MagicMock(return_value=_AsyncIter([msg]))
    channel.send = AsyncMock()

    cog.bot._register_server = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)

    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        i = mock_interaction()
        await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, True)
    assert "Imported" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_import_forbidden_read(cog):
    channel = MagicMock()
    channel.history = MagicMock(side_effect=discord.Forbidden(MagicMock(), "no"))

    cog.bot._register_server = AsyncMock()
    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        i = mock_interaction()
        with patch("bot.commands.quotebook.send_error", new_callable=AsyncMock) as se:
            await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, True)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_random_cache_hit(cog):
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = [{"quote_text": "Hi", "attribution": None}]
    i = mock_interaction()
    await cog.quote_group.random_cmd.callback(cog.quote_group, i)
    cog.bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_random_db_miss_sets_cache_when_present(cog):
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = None
    pool, _ = mock_db_pool(fetch=[{"quote_text": "Hi", "attribution": None}])
    cog.bot.db_pool = pool
    i = mock_interaction()
    await cog.quote_group.random_cmd.callback(cog.quote_group, i)
    cog.bot.cache.set.assert_called()


@pytest.mark.asyncio
async def test_import_skips_falsy_quote_text_from_parser(cog):
    cog.bot._register_server = AsyncMock()

    async def one_msg():
        m = MagicMock()
        m.author.bot = False
        yield m

    channel = MagicMock()
    channel.history = MagicMock(return_value=one_msg())
    channel.mention = "#quotes"
    channel.id = 44
    channel.send = AsyncMock()

    pool, conn = mock_db_pool(fetch=[])
    cog.bot.db_pool = pool

    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        with patch(
            "bot.commands.quotebook._parse_quotes_from_message",
            return_value=[("", None)],
        ):
            i = mock_interaction()
            await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, True)
    assert "Imported **0**" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_random_exception(cog):
    cog.bot.cache = None
    cog.bot.db_pool.acquire = MagicMock(side_effect=RuntimeError("db"))
    i = mock_interaction()
    with patch("bot.commands.quotebook.send_error", new_callable=AsyncMock) as se:
        await cog.quote_group.random_cmd.callback(cog.quote_group, i)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_fetch_quote_ids_and_approve_ids():
    pool, conn = mock_db_pool(fetch=[{"id": 1, "quote_text": "a", "approved": True}])
    rows = await _fetch_quote_ids(pool, 1)
    assert rows == conn.fetch.return_value
    pool2, conn2 = mock_db_pool(fetch=[{"id": 2, "quote_text": "b"}])
    rows2 = await _fetch_quote_approve_ids(pool2, 1)
    assert rows2 == conn2.fetch.return_value


def test_rows_to_choices_approved_labels():
    rows = [
        {"id": "550e8400-e29b-41d4-a716-446655440000", "quote_text": "x", "approved": True},
        {"id": "550e8400-e29b-41d4-a716-446655440001", "quote_text": "y", "approved": False},
    ]
    out = _rows_to_choices_with_approved(rows, "")
    assert any("✓" in c.name for c in out)
    assert any("pending" in c.name for c in out)


def test_rows_to_choices_plain_truncates():
    long_id = "12345678-1234-5678-1234-567812345678"
    rows = [{"id": long_id, "quote_text": "z" * 60}]
    out = _rows_to_choices(rows, "")
    assert len(out) == 1
    assert len(out[0].name) <= 100


@pytest.mark.asyncio
async def test_quote_autocomplete_wraps_cache(monkeypatch):
    async def fake_cached(interaction, current, cache_key, fetcher, mapper, **kw):
        return []

    monkeypatch.setattr(quotebook_mod, "cached_autocomplete", fake_cached)
    i = MagicMock()
    await _quote_id_autocomplete(i, "x")
    await _quote_id_approve_autocomplete(i, "y")


@pytest.mark.asyncio
async def test_list_not_admin(cog):
    with patch("bot.commands.quotebook.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.quote_group.list_cmd.callback(cog.quote_group, i)


@pytest.mark.asyncio
async def test_approve_not_admin(cog):
    with patch("bot.commands.quotebook.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.quote_group.approve_cmd.callback(
            cog.quote_group,
            i,
            "12345678-1234-5678-1234-567812345678",
        )


@pytest.mark.asyncio
async def test_approve_channel_unresolvable_logs(cog):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value={"quote_text": "Q", "attribution": None})
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    with patch("bot.commands.quotebook.get_quotebook_channel_id", AsyncMock(return_value=1)):
        with patch("bot.commands.quotebook.get_or_fetch_channel", AsyncMock(return_value=None)):
            with patch("bot.commands.quotebook.logger") as log:
                i = mock_interaction()
                await cog.quote_group.approve_cmd.callback(
                    cog.quote_group,
                    i,
                    "12345678-1234-5678-1234-567812345678",
                )
    log.warning.assert_called()


@pytest.mark.asyncio
async def test_delete_not_admin(cog):
    with patch("bot.commands.quotebook.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.quote_group.delete_cmd.callback(
            cog.quote_group,
            i,
            "12345678-1234-5678-1234-567812345678",
        )


@pytest.mark.asyncio
async def test_import_skips_bot_and_duplicates(cog):
    human = MagicMock()
    human.author.bot = False
    human.content = '"Hi" - Me'
    botmsg = MagicMock()
    botmsg.author.bot = True
    botmsg.content = '"Bot" - X'
    channel = MagicMock()
    channel.id = 9
    channel.mention = "#c"
    channel.history = MagicMock(return_value=_AsyncIter([botmsg, human, human]))
    channel.send = AsyncMock()
    cog.bot._register_server = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"quote_text": "Hi"}])
    conn.execute = AsyncMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        i = mock_interaction()
        await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, True)
    assert "Imported" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_import_channel_send_forbidden(cog):
    human = MagicMock()
    human.author.bot = False
    human.content = '"NewQuote" - A'
    channel = MagicMock()
    channel.id = 9
    channel.history = MagicMock(return_value=_AsyncIter([human]))
    channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no"))
    cog.bot._register_server = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        with patch("bot.commands.quotebook.logger"):
            i = mock_interaction()
            await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, True)


@pytest.mark.asyncio
async def test_import_generic_exception(cog):
    channel = MagicMock()
    channel.history = MagicMock(side_effect=RuntimeError("hist"))
    cog.bot._register_server = AsyncMock()
    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        i = mock_interaction()
        with patch("bot.commands.quotebook.send_error", new_callable=AsyncMock) as se:
            await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, True)
    se.assert_awaited()


def test_rows_to_choices_excludes_when_filter_mismatches():
    rows = [{"id": UUID(int=1), "quote_text": "hello"}]
    assert _rows_to_choices(rows, "nomatchxyz") == []


@pytest.mark.asyncio
async def test_import_not_admin(cog):
    channel = MagicMock()
    with patch("bot.commands.quotebook.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, True)


@pytest.mark.asyncio
async def test_import_auto_approve_false_skips_channel_posts(cog):
    human = MagicMock()
    human.author.bot = False
    human.content = '"Only" - Me'
    channel = MagicMock()
    channel.id = 9
    channel.history = MagicMock(return_value=_AsyncIter([human]))
    cog.bot._register_server = AsyncMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        i = mock_interaction()
        await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, False)
    assert not channel.send.called


@pytest.mark.asyncio
async def test_import_skips_falsy_quote_text_from_parsed_tuples(cog):
    human = MagicMock()
    human.author.bot = False
    human.content = '"ignored"'
    channel = MagicMock()
    channel.history = MagicMock(return_value=_AsyncIter([human]))
    cog.bot._register_server = AsyncMock()
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    with patch("bot.commands.quotebook.set_quotebook_channel", AsyncMock()):
        with patch(
            "bot.commands.quotebook._parse_quotes_from_message",
            return_value=[("", None), ("onlyreal", None)],
        ):
            i = mock_interaction()
            await cog.quote_group.import_cmd.callback(cog.quote_group, i, channel, False)
    assert conn.execute.await_count == 1


@pytest.mark.asyncio
async def test_approve_success_when_followup_row_missing(cog):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value=None)
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.quote_group.approve_cmd.callback(
        cog.quote_group,
        i,
        "12345678-1234-5678-1234-567812345678",
    )


@pytest.mark.asyncio
async def test_random_with_attribution_from_db(cog):
    cog.bot.cache = None
    conn = AsyncMock(
        fetch=AsyncMock(
            return_value=[{"quote_text": "Line", "attribution": "Author"}],
        )
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.quote_group.random_cmd.callback(cog.quote_group, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "Author" in (emb.description or "")


@pytest.mark.asyncio
async def test_random_caches_rows_after_db_fetch_when_cache_enabled(cog):
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = None
    conn = AsyncMock(
        fetch=AsyncMock(
            return_value=[{"quote_text": "Hi", "attribution": None}],
        )
    )
    cog.bot.db_pool.acquire.return_value = mock_db_ctx(conn)
    i = mock_interaction()
    await cog.quote_group.random_cmd.callback(cog.quote_group, i)
    cog.bot.cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_random_cache_hit_includes_attribution(cog):
    cog.bot.cache = MagicMock()
    cog.bot.cache.get.return_value = [{"quote_text": "Cached", "attribution": "By"}]
    i = mock_interaction()
    await cog.quote_group.random_cmd.callback(cog.quote_group, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "By" in (emb.description or "")


@pytest.mark.asyncio
async def test_quotebook_setup():
    bot = build_quotebook_bot()
    bot.tree.add_command = MagicMock()
    bot.tree.remove_command = MagicMock()
    c = QuotebookCommands(bot)
    await c.cog_load()
    await c.cog_unload()
    from bot.commands import quotebook as qb_mod

    bot.add_cog = AsyncMock()
    await qb_mod.setup(bot)
    bot.add_cog.assert_awaited_once()
