from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord import app_commands

from bot.commands.whitelist import OPERATION_CHOICES, WhitelistCommands, _validate_username
from bot.services.minecraft_rcon import MinecraftRCONError, TargetPushResult
from bot.utils.whitelist_cache import SyncFromRconResult
from tests.helpers import (
    assert_followup_contains,
    build_whitelist_bot,
    invoke,
    mock_db_pool,
    mock_interaction,
)


def _op_choice(value: str) -> app_commands.Choice[str]:
    return next(c for c in OPERATION_CHOICES if c.value == value)


class TestValidateUsername:
    @pytest.mark.parametrize("name", ["Steve", "Mr_Curls", "Player123", "a" * 16])
    def test_valid(self, name):
        assert _validate_username(name) == name

    def test_too_short(self):
        assert _validate_username("ab") is None

    def test_too_long(self):
        assert _validate_username("a" * 17) is None

    @pytest.mark.parametrize("name", ["Steve!", "Player-1", "with space"])
    def test_invalid_chars(self, name):
        assert _validate_username(name) is None

    def test_strips_whitespace(self):
        assert _validate_username("  Steve  ") == "Steve"


class TestSetWhitelistChannel:
    @pytest.mark.asyncio
    async def test_channel_cmd_set_success(self):
        with (
            patch(
                "bot.commands.whitelist.get_whitelist_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "bot.commands.whitelist.set_whitelist_channel",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            channel = MagicMock(id=999)
            await invoke(cog, "whitelist_cmd", None, i, channel=channel)
            assert_followup_contains(i, "set", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_clear_channel_success(self):
        with (
            patch(
                "bot.commands.whitelist.get_whitelist_channel_id",
                new_callable=AsyncMock,
                return_value=888,
            ),
            patch(
                "bot.commands.whitelist.set_whitelist_channel",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("clear_channel"),
                username=None,
                channel=None,
            )
            assert_followup_contains(i, "disabled", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_clear_channel_already_disabled(self):
        with patch(
            "bot.commands.whitelist.get_whitelist_channel_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("clear_channel"),
                username=None,
                channel=None,
            )
            assert_followup_contains(i, "already disabled", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_no_params_shows_help(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=None,
            username=None,
            channel=None,
        )
        assert_followup_contains(i, "Provide operation", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_operation_set_without_channel(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("set"),
            username=None,
            channel=None,
        )
        assert_followup_contains(i, "Channel required", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_operation_set_with_channel(self):
        with (
            patch(
                "bot.commands.whitelist.get_whitelist_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "bot.commands.whitelist.set_whitelist_channel",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            channel = MagicMock(id=999)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("set"),
                username=None,
                channel=channel,
            )
            assert_followup_contains(i, "set", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_channel_param_takes_precedence_over_operation(self):
        with (
            patch(
                "bot.commands.whitelist.get_whitelist_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "bot.commands.whitelist.set_whitelist_channel",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            channel = MagicMock(id=999)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("add"),
                username="Steve",
                channel=channel,
            )
            bot.minecraft_rcon.whitelist_add.assert_not_awaited()
            assert_followup_contains(i, "channel set", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_channel_cmd_same_as_current(self):
        with patch(
            "bot.commands.whitelist.get_whitelist_channel_id",
            new_callable=AsyncMock,
            return_value=999,
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            channel = MagicMock(id=999)
            await invoke(cog, "whitelist_cmd", None, i, channel=channel)
            assert_followup_contains(i, "already", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_run_on_toggles_whitelist(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("on"),
            username=None,
        )
        bot.minecraft_rcon.whitelist_on.assert_awaited_once()
        assert_followup_contains(i, "Whitelist:", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_run_off_toggles_whitelist(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("off"),
            username=None,
        )
        bot.minecraft_rcon.whitelist_off.assert_awaited_once()
        assert_followup_contains(i, "Whitelist:", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_run_on_requires_admin(self):
        bot = build_whitelist_bot()
        bot.permission_checker.check_role = AsyncMock(return_value=False)
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("on"),
            username=None,
        )
        bot.minecraft_rcon.whitelist_on.assert_not_awaited()
        assert_followup_contains(i, "Admin", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_run_off_requires_admin(self):
        bot = build_whitelist_bot()
        bot.permission_checker.check_role = AsyncMock(return_value=False)
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("off"),
            username=None,
        )
        bot.minecraft_rcon.whitelist_off.assert_not_awaited()
        assert_followup_contains(i, "Admin", case_sensitive=False)


class TestWhitelistList:
    @pytest.mark.asyncio
    async def test_list_success(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("list"),
            username=None,
        )
        bot.minecraft_rcon.whitelist_list.assert_awaited_once()
        assert_followup_contains(i, "Whitelist:")


class TestWhitelistAdd:
    @pytest.mark.asyncio
    async def test_add_success(self):
        with (
            patch(
                "bot.commands.whitelist.get_profile",
                new_callable=AsyncMock,
                return_value=("uuid", "Steve"),
            ),
            patch("bot.commands.whitelist.add_to_cache", new_callable=AsyncMock),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("add"),
                username="Steve",
            )
            bot.minecraft_rcon.whitelist_add.assert_awaited_once_with("Steve")

    @pytest.mark.asyncio
    async def test_add_invalid_username(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("add"),
            username="ab",
        )
        bot.minecraft_rcon.whitelist_add.assert_not_awaited()
        assert_followup_contains(i, "Invalid")

    @pytest.mark.asyncio
    async def test_add_no_username(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("add"),
            username=None,
        )
        bot.minecraft_rcon.whitelist_add.assert_not_awaited()
        assert_followup_contains(i, "Username required")

    @pytest.mark.asyncio
    async def test_add_no_rcon(self):
        bot = build_whitelist_bot()
        bot.minecraft_rcon = None
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("add"),
            username="Steve",
        )
        assert_followup_contains(i, "not configured", case_sensitive=False)


class TestWhitelistRemove:
    @pytest.mark.asyncio
    async def test_remove_success(self):
        with patch("bot.commands.whitelist.remove_from_cache", new_callable=AsyncMock):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("remove"),
                username="Steve",
            )
            bot.minecraft_rcon.whitelist_remove.assert_awaited_once_with("Steve")

    @pytest.mark.asyncio
    async def test_remove_invalid_username(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("remove"),
            username="x",
        )
        bot.minecraft_rcon.whitelist_remove.assert_not_awaited()
        assert_followup_contains(i, "Invalid")

    @pytest.mark.asyncio
    async def test_remove_no_rcon(self):
        bot = build_whitelist_bot()
        bot.minecraft_rcon = None
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("remove"),
            username="Steve",
        )
        assert_followup_contains(i, "not configured", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_remove_retries_current_mojang_name(self):
        with (
            patch("bot.commands.whitelist.remove_from_cache", new_callable=AsyncMock),
            patch(
                "bot.commands.whitelist.get_cache_entry",
                new_callable=AsyncMock,
                return_value={
                    "username": "Old",
                    "minecraft_uuid": "069a79f4-44e9-4726-a5be-fca90e38aaf5",
                },
            ),
            patch(
                "bot.commands.whitelist.get_profile_by_uuid",
                new_callable=AsyncMock,
                return_value=(
                    "069a79f4-44e9-4726-a5be-fca90e38aaf5",
                    "NewName",
                ),
            ),
        ):
            bot = build_whitelist_bot()
            bot.minecraft_rcon.whitelist_remove = AsyncMock(
                side_effect=[
                    "That player is not whitelisted",
                    "Removed NewName from the whitelist",
                ]
            )
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("remove"),
                username="Old",
            )
            assert bot.minecraft_rcon.whitelist_remove.await_count == 2
            bot.minecraft_rcon.whitelist_remove.assert_any_call("NewName")

    @pytest.mark.asyncio
    async def test_remove_stale_without_uuid_prompts_repair(self):
        with (
            patch("bot.commands.whitelist.remove_from_cache", new_callable=AsyncMock) as rm,
            patch(
                "bot.commands.whitelist.get_cache_entry", new_callable=AsyncMock, return_value=None
            ),
        ):
            bot = build_whitelist_bot()
            bot.minecraft_rcon.whitelist_remove = AsyncMock(
                return_value="Nothing changed. Not whitelisted."
            )
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("remove"),
                username="Ghost",
            )
            rm.assert_not_awaited()
            assert_followup_contains(i, "Repair", case_sensitive=False)


class TestWhitelistSync:
    @pytest.mark.asyncio
    async def test_reload_success(self):
        with (
            patch(
                "bot.commands.whitelist.sync_from_rcon",
                new_callable=AsyncMock,
                return_value=SyncFromRconResult(
                    ok=True, player_count=2, reachable_targets=1, unreachable_target_ids=()
                ),
            ),
            patch(
                "bot.commands.whitelist.get_cached_usernames",
                new_callable=AsyncMock,
                return_value=["Steve", "Alex"],
            ),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("sync"),
                username=None,
            )
            assert_followup_contains(i, "Synced")

    @pytest.mark.asyncio
    async def test_reload_failure(self):
        with patch(
            "bot.commands.whitelist.sync_from_rcon",
            new_callable=AsyncMock,
            return_value=SyncFromRconResult(ok=False),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("sync"),
                username=None,
            )
            assert_followup_contains(i, "Failed")

    @pytest.mark.asyncio
    async def test_reload_warns_when_some_servers_unreachable(self):
        with (
            patch(
                "bot.commands.whitelist.sync_from_rcon",
                new_callable=AsyncMock,
                return_value=SyncFromRconResult(
                    ok=True,
                    player_count=1,
                    reachable_targets=1,
                    unreachable_target_ids=("offline",),
                ),
            ),
            patch(
                "bot.commands.whitelist.get_cached_usernames",
                new_callable=AsyncMock,
                return_value=["Steve"],
            ),
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("sync"),
                username=None,
            )
            assert_followup_contains(i, "unreachable", case_sensitive=False)
            assert_followup_contains(i, "logs", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_reload_no_rcon(self):
        bot = build_whitelist_bot()
        bot.minecraft_rcon = None
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=_op_choice("sync"),
            username=None,
        )
        assert_followup_contains(i, "not configured", case_sensitive=False)


class TestWhitelistRepair:
    @pytest.mark.asyncio
    async def test_repair_shows_renamed_summary(self):
        with patch(
            "bot.commands.whitelist.reconcile_whitelist_cache",
            new_callable=AsyncMock,
            return_value={"updated": ["Old → New"], "uuid_filled": [], "pruned": []},
        ):
            bot = build_whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("repair"),
                username=None,
            )
            assert_followup_contains(i, "Renamed", case_sensitive=False)


class TestWhitelistPush:
    @pytest.mark.asyncio
    async def test_push_success(self):
        bot = build_whitelist_bot()
        bot.minecraft_rcon.push_master_whitelist = AsyncMock(
            return_value=[TargetPushResult(target_id="default", added=["a"], removed=[])]
        )
        with patch(
            "bot.commands.whitelist.get_cached_usernames",
            new_callable=AsyncMock,
            return_value=["Steve"],
        ):
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("push"),
                username=None,
            )
            bot.minecraft_rcon.push_master_whitelist.assert_awaited_once()
            assert_followup_contains(i, "default", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_push_empty_master(self):
        bot = build_whitelist_bot()
        with patch(
            "bot.commands.whitelist.get_cached_usernames",
            new_callable=AsyncMock,
            return_value=[],
        ):
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("push"),
                username=None,
            )
            bot.minecraft_rcon.push_master_whitelist.assert_not_awaited()
            assert_followup_contains(i, "empty", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_push_rcon_error(self):
        bot = build_whitelist_bot()
        bot.minecraft_rcon.push_master_whitelist = AsyncMock(side_effect=MinecraftRCONError("down"))
        with patch(
            "bot.commands.whitelist.get_cached_usernames",
            new_callable=AsyncMock,
            return_value=["Steve"],
        ):
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            await invoke(
                cog,
                "whitelist_cmd",
                None,
                i,
                operation=_op_choice("push"),
                username=None,
            )
            assert_followup_contains(i, "Could not", case_sensitive=False)


class TestWhitelistDispatch:
    @pytest.mark.asyncio
    async def test_unknown_operation_returns_error(self):
        bot = build_whitelist_bot()
        bot.db_pool, _ = mock_db_pool()
        cog = WhitelistCommands(bot)
        i = mock_interaction(user_id=2)
        i.guild = MagicMock()
        await invoke(
            cog,
            "whitelist_cmd",
            None,
            i,
            operation=app_commands.Choice(name="Unknown", value="unknown"),
            username=None,
            channel=None,
        )
        assert_followup_contains(i, "Unknown operation.")
