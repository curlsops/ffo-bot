from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from bot.commands.reaction_roles import (
    ReactionRoleCommands,
    _invalidate_reaction_role_cache,
    _parse_required_message_ref,
)
from tests.helpers import assert_followup_contains, invoke, mock_db_pool, mock_interaction

_OP_ADD = app_commands.Choice(name="Add", value="add")
_OP_LIST = app_commands.Choice(name="List", value="list")
_OP_REMOVE = app_commands.Choice(name="Remove", value="remove")


def test_invalidate_cache_no_cache():
    _invalidate_reaction_role_cache(None, 1, 2, "👍")


def test_invalidate_cache_deletes():
    c = MagicMock()
    _invalidate_reaction_role_cache(c, 9, 8, "x")
    assert c.delete.call_count >= 2


@pytest.mark.asyncio
async def test_parse_required_message_ref_empty():
    i = mock_interaction()
    with patch("bot.commands.reaction_roles.send_error", new_callable=AsyncMock) as se:
        out = await _parse_required_message_ref(i, None)
    assert out is None
    se.assert_awaited()


@pytest.mark.asyncio
async def test_parse_required_message_ref_invalid():
    i = mock_interaction()
    with patch("bot.commands.reaction_roles.send_error", new_callable=AsyncMock) as se:
        out = await _parse_required_message_ref(i, "not-a-link-or-id")
    assert out is None
    se.assert_awaited()


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.cache = None
    bot.notifier = MagicMock()
    bot.notifier.notify_reaction_role_setup = AsyncMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    pool, _ = mock_db_pool()
    bot.db_pool = pool
    return bot


@pytest.fixture
def cog(mock_bot):
    return ReactionRoleCommands(mock_bot)


@pytest.mark.asyncio
async def test_list_cache_hit(cog, mock_bot):
    mock_bot.cache = MagicMock()
    mock_bot.cache.get.return_value = [
        {"message_id": 1, "channel_id": 2, "emoji": "👍", "role_id": 9}
    ]
    mock_bot.db_pool = MagicMock()
    i = mock_interaction()
    await invoke(cog, "reactionrole_cmd", None, i, operation=_OP_LIST)
    mock_bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_list_sets_cache_after_fetch(cog, mock_bot):
    mock_bot.cache = MagicMock()
    mock_bot.cache.get.return_value = None
    pool, _ = mock_db_pool(
        fetch=[{"message_id": 1, "channel_id": 2, "emoji": "👍", "role_id": 9}],
    )
    mock_bot.db_pool = pool
    i = mock_interaction()
    await invoke(cog, "reactionrole_cmd", None, i, operation=_OP_LIST)
    mock_bot.cache.set.assert_called()


@pytest.mark.asyncio
async def test_list_exception(cog, mock_bot):
    mock_bot.db_pool.acquire = MagicMock(side_effect=RuntimeError("db"))
    i = mock_interaction()
    with patch("bot.commands.reaction_roles.send_error", new_callable=AsyncMock) as se:
        await invoke(cog, "reactionrole_cmd", None, i, operation=_OP_LIST)
    se.assert_awaited()


@pytest.mark.asyncio
async def test_add_missing_fields(cog):
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_ADD,
        message=None,
        emoji="👍",
        role=MagicMock(),
    )
    assert_followup_contains(i, "required")


@pytest.mark.asyncio
async def test_add_channel_not_found(cog, mock_bot):
    mock_bot.get_channel = MagicMock(return_value=None)
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_ADD,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
        role=MagicMock(id=1),
    )
    assert_followup_contains(i, "Channel not found")


@pytest.mark.asyncio
async def test_add_message_not_found(cog, mock_bot):
    ch = MagicMock()
    ch.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    mock_bot.get_channel = MagicMock(return_value=ch)
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_ADD,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
        role=MagicMock(id=1),
    )
    assert_followup_contains(i, "not found")


@pytest.mark.asyncio
async def test_add_reaction_http_error(cog, mock_bot):
    msg = MagicMock(add_reaction=AsyncMock(side_effect=discord.HTTPException(MagicMock(), "no")))
    ch = MagicMock(fetch_message=AsyncMock(return_value=msg))
    mock_bot.get_channel = MagicMock(return_value=ch)
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_ADD,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
        role=MagicMock(id=1, mention="<@&1>"),
    )
    assert_followup_contains(i, "Cannot add")


@pytest.mark.asyncio
async def test_add_updates_existing_row(cog, mock_bot):
    msg = MagicMock(add_reaction=AsyncMock())
    ch = MagicMock(fetch_message=AsyncMock(return_value=msg))
    mock_bot.get_channel = MagicMock(return_value=ch)
    pool, conn = mock_db_pool(fetchval=42)
    conn.execute = AsyncMock()
    mock_bot.db_pool = pool
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_ADD,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
        role=MagicMock(id=99, mention="<@&99>"),
    )
    conn.execute.assert_awaited()


@pytest.mark.asyncio
async def test_add_outer_exception(cog, mock_bot):
    mock_bot.get_channel = MagicMock(side_effect=RuntimeError("x"))
    i = mock_interaction()
    with patch("bot.commands.reaction_roles.send_error", new_callable=AsyncMock) as se:
        await invoke(
            cog,
            "reactionrole_cmd",
            None,
            i,
            operation=_OP_ADD,
            message="https://discord.com/channels/1/2/123",
            emoji="👍",
            role=MagicMock(id=1),
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_remove_missing_fields(cog):
    i = mock_interaction()
    await invoke(cog, "reactionrole_cmd", None, i, operation=_OP_REMOVE, message=None, emoji="👍")
    assert_followup_contains(i, "required")


@pytest.mark.asyncio
async def test_remove_success_with_notifier_and_clear_reaction(cog, mock_bot):
    pool, conn = mock_db_pool(execute="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value={"role_id": 55})
    mock_bot.db_pool = pool
    ch = MagicMock()
    msg = MagicMock(clear_reaction=AsyncMock())
    ch.fetch_message = AsyncMock(return_value=msg)
    mock_bot.get_channel = MagicMock(return_value=ch)
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_REMOVE,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
    )
    mock_bot.notifier.notify_reaction_role_setup.assert_awaited()
    msg.clear_reaction.assert_awaited()


@pytest.mark.asyncio
async def test_remove_clear_reaction_swallows_errors(cog, mock_bot):
    pool, conn = mock_db_pool(execute="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value={"role_id": 55})
    mock_bot.db_pool = pool
    ch = MagicMock()
    ch.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "x"))
    mock_bot.get_channel = MagicMock(return_value=ch)
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_REMOVE,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
    )


@pytest.mark.asyncio
async def test_remove_exception_outer(cog, mock_bot):
    mock_bot.db_pool.acquire = MagicMock(side_effect=RuntimeError("db"))
    i = mock_interaction()
    with patch("bot.commands.reaction_roles.send_error", new_callable=AsyncMock) as se:
        await invoke(
            cog,
            "reactionrole_cmd",
            None,
            i,
            operation=_OP_REMOVE,
            message="https://discord.com/channels/1/2/123",
            emoji="👍",
        )
    se.assert_awaited()


@pytest.mark.asyncio
async def test_add_require_admin_false(cog, mock_bot):
    mock_bot.db_pool = MagicMock()
    with patch("bot.commands.reaction_roles.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await invoke(
            cog,
            "reactionrole_cmd",
            None,
            i,
            operation=_OP_ADD,
            message="https://discord.com/channels/1/2/123",
            emoji="👍",
            role=MagicMock(),
        )
    mock_bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_add_success_without_notifier(cog, mock_bot):
    mock_bot.notifier = None
    msg = MagicMock(add_reaction=AsyncMock())
    ch = MagicMock(fetch_message=AsyncMock(return_value=msg))
    mock_bot.get_channel = MagicMock(return_value=ch)
    pool, conn = mock_db_pool(fetchval=None)
    mock_bot.db_pool = pool
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_ADD,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
        role=MagicMock(id=1, mention="<@&1>"),
    )


@pytest.mark.asyncio
async def test_remove_without_notifier_skips_notify(cog, mock_bot):
    mock_bot.notifier = None
    pool, conn = mock_db_pool(execute="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value={"role_id": 55})
    mock_bot.db_pool = pool
    ch = MagicMock()
    ch.fetch_message = AsyncMock(return_value=MagicMock(clear_reaction=AsyncMock()))
    mock_bot.get_channel = MagicMock(return_value=ch)
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_REMOVE,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
    )


@pytest.mark.asyncio
async def test_remove_channel_none_skips_clear(cog, mock_bot):
    pool, conn = mock_db_pool(execute="UPDATE 1")
    conn.fetchrow = AsyncMock(return_value={"role_id": 55})
    mock_bot.db_pool = pool
    mock_bot.get_channel = MagicMock(return_value=None)
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_REMOVE,
        message="https://discord.com/channels/1/2/123",
        emoji="👍",
    )


@pytest.mark.asyncio
async def test_remove_invalid_message_returns_early(cog, mock_bot):
    mock_bot.db_pool = MagicMock()
    i = mock_interaction()
    await invoke(
        cog,
        "reactionrole_cmd",
        None,
        i,
        operation=_OP_REMOVE,
        message="not-a-link",
        emoji="👍",
    )
    mock_bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_reactionrole_unknown_operation(cog, mock_bot):
    mock_bot.db_pool = MagicMock()
    i = mock_interaction()
    bad = app_commands.Choice(name="Bad", value="nope")
    await invoke(cog, "reactionrole_cmd", None, i, operation=bad)


@pytest.mark.asyncio
async def test_remove_require_admin_false(cog, mock_bot):
    mock_bot.db_pool = MagicMock()
    with patch("bot.commands.reaction_roles.require_admin", AsyncMock(return_value=False)):
        i = mock_interaction()
        await invoke(
            cog,
            "reactionrole_cmd",
            None,
            i,
            operation=_OP_REMOVE,
            message="https://discord.com/channels/1/2/123",
            emoji="👍",
        )
    mock_bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_reaction_role_cog_load(mock_bot):
    mock_bot.tree.add_command = MagicMock()
    cog = ReactionRoleCommands(mock_bot)
    await cog.cog_load()
    mock_bot.tree.remove_command = MagicMock()
    await cog.cog_unload()

    from bot.commands import reaction_roles as rr

    mock_bot.add_cog = AsyncMock()
    await rr.setup(mock_bot)
    mock_bot.add_cog.assert_awaited_once()
