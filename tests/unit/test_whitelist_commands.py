from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord import app_commands

from bot.commands.whitelist import OPERATION_CHOICES, WhitelistCommands, _validate_username
from tests.helpers import assert_followup_contains, invoke, mock_db_pool, mock_interaction


def _whitelist_bot():
    bot = MagicMock()
    bot.cache = None
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot._register_server = AsyncMock()
    bot.minecraft_rcon = MagicMock()
    bot.minecraft_rcon._is_configured = MagicMock(return_value=True)
    bot.minecraft_rcon.whitelist_add = AsyncMock(return_value="Added")
    bot.minecraft_rcon.whitelist_remove = AsyncMock(return_value="Removed")
    bot.minecraft_rcon.whitelist_list = AsyncMock(return_value="Steve, Alex")
    bot.minecraft_rcon.whitelist_on = AsyncMock(return_value="Whitelist is now turned on")
    bot.minecraft_rcon.whitelist_off = AsyncMock(return_value="Whitelist is now turned off")
    return bot


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
            bot = _whitelist_bot()
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
            bot = _whitelist_bot()
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
            bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
    async def test_channel_cmd_same_as_current(self):
        with patch(
            "bot.commands.whitelist.get_whitelist_channel_id",
            new_callable=AsyncMock,
            return_value=999,
        ):
            bot = _whitelist_bot()
            bot.db_pool, _ = mock_db_pool()
            cog = WhitelistCommands(bot)
            i = mock_interaction(user_id=2)
            i.guild = MagicMock()
            channel = MagicMock(id=999)
            await invoke(cog, "whitelist_cmd", None, i, channel=channel)
            assert_followup_contains(i, "already", case_sensitive=False)

    @pytest.mark.asyncio
    async def test_run_on_toggles_whitelist(self):
        bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
            bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
            bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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
        bot = _whitelist_bot()
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


class TestWhitelistSync:
    @pytest.mark.asyncio
    async def test_reload_success(self):
        with (
            patch(
                "bot.commands.whitelist.sync_from_rcon",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "bot.commands.whitelist.get_cached_usernames",
                new_callable=AsyncMock,
                return_value=["Steve", "Alex"],
            ),
        ):
            bot = _whitelist_bot()
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
            return_value=False,
        ):
            bot = _whitelist_bot()
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
    async def test_reload_no_rcon(self):
        bot = _whitelist_bot()
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
