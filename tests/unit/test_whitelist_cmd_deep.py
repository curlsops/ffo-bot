from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord import app_commands

from bot.commands.whitelist import WhitelistCommands, _whitelist_username_autocomplete
from bot.services.minecraft_rcon import MinecraftRCONError, TargetPushResult
from tests.helpers import (
    assert_followup_contains,
    build_whitelist_bot,
    invoke,
    mock_db_pool,
    mock_interaction,
)


def _op(v: str) -> app_commands.Choice[str]:
    return app_commands.Choice(name=v, value=v)


@pytest.mark.asyncio
async def test_username_autocomplete_no_guild_id():
    i = MagicMock(guild_id=None)
    assert await _whitelist_username_autocomplete(i, "a") == []


@pytest.mark.asyncio
async def test_username_autocomplete_no_rcon():
    bot = build_whitelist_bot()
    bot.minecraft_rcon = None
    i = MagicMock(guild_id=1, client=bot)
    assert await _whitelist_username_autocomplete(i, "s") == []


@pytest.mark.asyncio
async def test_username_autocomplete_syncs_when_empty_cache():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    with (
        patch(
            "bot.commands.whitelist.get_cached_usernames",
            new_callable=AsyncMock,
            side_effect=[[], ["Steve"]],
        ),
        patch("bot.commands.whitelist.sync_from_rcon", new_callable=AsyncMock) as sync,
    ):
        i = MagicMock(guild_id=1, client=bot)
        out = await _whitelist_username_autocomplete(i, "")
    sync.assert_awaited()
    assert out and out[0].value == "Steve"


@pytest.mark.asyncio
async def test_username_autocomplete_filters_current():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    with patch(
        "bot.commands.whitelist.get_cached_usernames",
        new_callable=AsyncMock,
        return_value=["Steve", "Alex"],
    ):
        i = MagicMock(guild_id=1, client=bot)
        out = await _whitelist_username_autocomplete(i, "ale")
    assert [c.value for c in out] == ["Alex"]


@pytest.mark.asyncio
async def test_toggle_rcon_error():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    bot.minecraft_rcon.whitelist_on = AsyncMock(side_effect=MinecraftRCONError("down"))
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    i.guild = MagicMock()
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("on"), username=None)
    assert_followup_contains(i, "RCON", case_sensitive=False)


@pytest.mark.asyncio
async def test_channel_set_failed_update():
    with (
        patch("bot.commands.whitelist.get_whitelist_channel_id", AsyncMock(return_value=None)),
        patch("bot.commands.whitelist.set_whitelist_channel", AsyncMock(return_value=False)),
    ):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        ch = MagicMock(id=12)
        await invoke(cog, "whitelist_cmd", None, i, channel=ch)
    assert_followup_contains(i, "Failed", case_sensitive=False)


@pytest.mark.asyncio
async def test_channel_set_without_notify_moderation():
    with (
        patch("bot.commands.whitelist.get_whitelist_channel_id", AsyncMock(return_value=None)),
        patch("bot.commands.whitelist.set_whitelist_channel", AsyncMock(return_value=True)),
    ):
        bot = build_whitelist_bot()
        bot.settings.feature_notify_moderation = False
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        ch = MagicMock(id=44, mention="#c")
        await invoke(cog, "whitelist_cmd", None, i, channel=ch)
    bot.notifier.notify_whitelist.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_clear_failed_update():
    with patch("bot.commands.whitelist.get_whitelist_channel_id", AsyncMock(return_value=9)):
        with patch("bot.commands.whitelist.set_whitelist_channel", AsyncMock(return_value=False)):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            await invoke(cog, "whitelist_cmd", None, i, operation=_op("clear_channel"))
    assert_followup_contains(i, "Failed", case_sensitive=False)


@pytest.mark.asyncio
async def test_channel_clear_without_notify():
    with patch("bot.commands.whitelist.get_whitelist_channel_id", AsyncMock(return_value=9)):
        with patch("bot.commands.whitelist.set_whitelist_channel", AsyncMock(return_value=True)):
            bot = build_whitelist_bot()
            bot.settings.feature_notify_moderation = False
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            await invoke(cog, "whitelist_cmd", None, i, operation=_op("clear_channel"))
    bot.notifier.notify_whitelist.assert_not_awaited()


@pytest.mark.asyncio
async def test_toggle_on_notifies():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    i.guild = MagicMock()
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("on"))
    bot.notifier.notify_whitelist.assert_awaited()


@pytest.mark.asyncio
async def test_add_rcon_error():
    bot = build_whitelist_bot()
    bot.minecraft_rcon.whitelist_add = AsyncMock(side_effect=MinecraftRCONError("x"))
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("add"), username="Steve")
    assert_followup_contains(i, "RCON", case_sensitive=False)


@pytest.mark.asyncio
async def test_add_without_notify():
    bot = build_whitelist_bot()
    bot.settings.feature_notify_moderation = False
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    with patch("bot.commands.whitelist.get_profile", AsyncMock(return_value=("u", "Steve"))):
        with patch("bot.commands.whitelist.add_to_cache", new_callable=AsyncMock):
            i = mock_interaction(user_id=2)
            await invoke(cog, "whitelist_cmd", None, i, operation=_op("add"), username="Steve")
    bot.notifier.notify_whitelist.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_empty_response():
    bot = build_whitelist_bot()
    bot.minecraft_rcon.whitelist_list = AsyncMock(return_value="")
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("list"))
    assert_followup_contains(i, "empty", case_sensitive=False)


@pytest.mark.asyncio
async def test_list_rcon_error():
    bot = build_whitelist_bot()
    bot.minecraft_rcon.whitelist_list = AsyncMock(side_effect=MinecraftRCONError("x"))
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("list"))
    assert_followup_contains(i, "RCON", case_sensitive=False)


@pytest.mark.asyncio
async def test_push_with_target_error_line():
    bot = build_whitelist_bot()
    bot.minecraft_rcon.push_master_whitelist = AsyncMock(
        return_value=[TargetPushResult(target_id="t1", added=[], removed=[], error="boom")]
    )
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    with patch(
        "bot.commands.whitelist.get_cached_usernames",
        new_callable=AsyncMock,
        return_value=["A"],
    ):
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("push"))
    assert_followup_contains(i, "error", case_sensitive=False)


@pytest.mark.asyncio
async def test_push_notify_without_feature_flag():
    bot = build_whitelist_bot()
    bot.settings.feature_notify_moderation = False
    bot.minecraft_rcon.push_master_whitelist = AsyncMock(
        return_value=[TargetPushResult(target_id="t1", added=["a"], removed=[])]
    )
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    with patch(
        "bot.commands.whitelist.get_cached_usernames",
        new_callable=AsyncMock,
        return_value=["Steve"],
    ):
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("push"))
    bot.notifier.notify_whitelist.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_uuid_and_prune_summaries():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    summary = {
        "updated": [],
        "uuid_filled": ["a"],
        "pruned": ["gone"],
    }
    with patch(
        "bot.commands.whitelist.reconcile_whitelist_cache",
        new_callable=AsyncMock,
        return_value=summary,
    ):
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("repair"))
    assert_followup_contains(i, "UUID", case_sensitive=False)
    assert_followup_contains(i, "stale", case_sensitive=False)


@pytest.mark.asyncio
async def test_repair_many_renames_truncates():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    many = [f"r{i}" for i in range(50)]
    with patch(
        "bot.commands.whitelist.reconcile_whitelist_cache",
        new_callable=AsyncMock,
        return_value={"updated": many, "uuid_filled": [], "pruned": []},
    ):
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("repair"))
    assert_followup_contains(i, "…", case_sensitive=False)


@pytest.mark.asyncio
async def test_repair_without_notify():
    bot = build_whitelist_bot()
    bot.settings.feature_notify_moderation = False
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    with patch(
        "bot.commands.whitelist.reconcile_whitelist_cache",
        new_callable=AsyncMock,
        return_value={"updated": [], "uuid_filled": [], "pruned": []},
    ):
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("repair"))
    bot.notifier.notify_whitelist.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_second_try_same_name_no_retry():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    with (
        patch("bot.commands.whitelist.remove_from_cache", new_callable=AsyncMock),
        patch(
            "bot.commands.whitelist.get_cache_entry",
            new_callable=AsyncMock,
            return_value={"minecraft_uuid": "u", "username": "Old"},
        ),
        patch(
            "bot.commands.whitelist.get_profile_by_uuid",
            new_callable=AsyncMock,
            return_value=("u", "old"),
        ),
    ):
        bot.minecraft_rcon.whitelist_remove = AsyncMock(
            return_value="That player is not whitelisted"
        )
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("remove"), username="Old")
    assert bot.minecraft_rcon.whitelist_remove.await_count == 1


@pytest.mark.asyncio
async def test_remove_success_without_notify():
    bot = build_whitelist_bot()
    bot.settings.feature_notify_moderation = False
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    with patch("bot.commands.whitelist.remove_from_cache", new_callable=AsyncMock):
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("remove"), username="Steve")
    bot.notifier.notify_whitelist.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_rcon_error():
    bot = build_whitelist_bot()
    bot.minecraft_rcon.whitelist_remove = AsyncMock(side_effect=MinecraftRCONError("x"))
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("remove"), username="Steve")
    assert_followup_contains(i, "RCON", case_sensitive=False)


@pytest.mark.asyncio
async def test_mod_ops_require_rcon():
    bot = build_whitelist_bot()
    bot.minecraft_rcon = None
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("list"))
    assert_followup_contains(i, "not configured", case_sensitive=False)


@pytest.mark.asyncio
async def test_toggle_requires_rcon_configured():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    i.guild = MagicMock()
    with patch("bot.commands.whitelist.require_rcon", AsyncMock(return_value=False)):
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("on"))
    bot.minecraft_rcon.whitelist_on.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_stops_when_require_rcon_false():
    bot = build_whitelist_bot()
    bot.db_pool = MagicMock()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    with patch("bot.commands.whitelist.require_rcon", AsyncMock(return_value=False)):
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("sync"))
    bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_channel_set_requires_admin():
    with (
        patch("bot.commands.whitelist.get_whitelist_channel_id", AsyncMock(return_value=None)),
        patch("bot.commands.whitelist.set_whitelist_channel", AsyncMock(return_value=True)),
    ):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        ch = MagicMock(id=12)
        with patch("bot.commands.whitelist.require_admin", AsyncMock(return_value=False)):
            await invoke(cog, "whitelist_cmd", None, i, channel=ch)
    bot._register_server.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_clear_requires_admin():
    with patch("bot.commands.whitelist.get_whitelist_channel_id", AsyncMock(return_value=9)):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        with patch("bot.commands.whitelist.require_admin", AsyncMock(return_value=False)):
            await invoke(cog, "whitelist_cmd", None, i, operation=_op("clear_channel"))


@pytest.mark.asyncio
async def test_list_many_players_paginated():
    bot = build_whitelist_bot()
    names = ", ".join(f"Player{n}" for n in range(30))
    bot.minecraft_rcon.whitelist_list = AsyncMock(
        return_value=f"There are 30 whitelisted players: {names}"
    )
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("list"))
    assert i.followup.send.call_args.kwargs.get("view") is not None


@pytest.mark.asyncio
async def test_remove_missing_username_message():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("remove"), username=None)
    assert_followup_contains(i, "Username required", case_sensitive=False)


@pytest.mark.asyncio
async def test_remove_invalid_username_message():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("remove"), username="!!")
    assert_followup_contains(i, "Invalid username", case_sensitive=False)


@pytest.mark.asyncio
async def test_moderation_requires_mod_role():
    bot = build_whitelist_bot()
    bot.db_pool = MagicMock()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    with patch("bot.commands.whitelist.require_mod", AsyncMock(return_value=False)):
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("sync"))
    bot.db_pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_skips_notify_when_feature_off():
    bot = build_whitelist_bot()
    bot.settings.feature_notify_moderation = False
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    i = mock_interaction(user_id=2)
    i.guild = MagicMock()
    await invoke(cog, "whitelist_cmd", None, i, operation=_op("off"))
    bot.notifier.notify_whitelist.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_retries_then_succeeds_on_second_name():
    bot = build_whitelist_bot()
    bot.db_pool, _ = mock_db_pool()
    cog = WhitelistCommands(bot)
    with (
        patch("bot.commands.whitelist.remove_from_cache", new_callable=AsyncMock),
        patch(
            "bot.commands.whitelist.get_cache_entry",
            new_callable=AsyncMock,
            return_value={"minecraft_uuid": "u", "username": "Old"},
        ),
        patch(
            "bot.commands.whitelist.get_profile_by_uuid",
            new_callable=AsyncMock,
            return_value=("u", "NewName"),
        ),
    ):
        bot.minecraft_rcon.whitelist_remove = AsyncMock(
            side_effect=[
                "That player is not whitelisted",
                "Removed NewName from the whitelist",
            ]
        )
        i = mock_interaction(user_id=2)
        await invoke(cog, "whitelist_cmd", None, i, operation=_op("remove"), username="Old")
    assert bot.minecraft_rcon.whitelist_remove.await_count == 2


@pytest.mark.asyncio
async def test_whitelist_cog_load_unload():
    bot = build_whitelist_bot()
    bot.tree.add_command = MagicMock()
    cog = WhitelistCommands(bot)
    await cog.cog_load()
    bot.tree.remove_command = MagicMock()
    await cog.cog_unload()
    from bot.commands import whitelist as wl

    bot.add_cog = AsyncMock()
    await wl.setup(bot)
    bot.add_cog.assert_awaited_once()
