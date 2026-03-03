"""Tests for whitelist slash commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.whitelist import WhitelistCommands, _validate_username


def make_bot():
    bot = MagicMock()
    bot.cache = None
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot._register_server = AsyncMock()
    bot.minecraft_rcon = MagicMock()
    bot.minecraft_rcon._is_configured = MagicMock(return_value=True)
    bot.minecraft_rcon.whitelist_add = AsyncMock(return_value="Added")
    bot.minecraft_rcon.whitelist_remove = AsyncMock(return_value="Removed")
    bot.minecraft_rcon.whitelist_list = AsyncMock(return_value="Steve, Alex")
    return bot


def make_db_pool(conn=None):
    conn = conn or MagicMock(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool, conn


def make_interaction(guild_id=1, user_id=2):
    i = MagicMock(guild_id=guild_id, channel_id=3)
    i.user = MagicMock(id=user_id)
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


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
    async def test_set_channel_success(self):
        with patch(
            "bot.commands.whitelist.get_whitelist_channel_id",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "bot.commands.whitelist.set_whitelist_channel",
            new_callable=AsyncMock,
            return_value=True,
        ):
            bot = make_bot()
            bot.db_pool, _ = make_db_pool()
            cog = WhitelistCommands(bot)
            i = make_interaction()
            i.guild = MagicMock()
            channel = MagicMock(id=999)
            await cog.set_whitelist_channel_cmd.callback(cog, i, channel)
            assert "set" in str(i.followup.send.call_args[0][0]).lower()

    @pytest.mark.asyncio
    async def test_set_channel_same_as_current(self):
        with patch(
            "bot.commands.whitelist.get_whitelist_channel_id",
            new_callable=AsyncMock,
            return_value=999,
        ):
            bot = make_bot()
            bot.db_pool, _ = make_db_pool()
            cog = WhitelistCommands(bot)
            i = make_interaction()
            i.guild = MagicMock()
            channel = MagicMock(id=999)
            await cog.set_whitelist_channel_cmd.callback(cog, i, channel)
            assert "already" in str(i.followup.send.call_args[0][0]).lower()


class TestWhitelistList:
    @pytest.mark.asyncio
    async def test_list_success(self):
        bot = make_bot()
        bot.db_pool, _ = make_db_pool()
        cog = WhitelistCommands(bot)
        i = make_interaction()
        await cog.whitelist_list.callback(cog, i)
        bot.minecraft_rcon.whitelist_list.assert_awaited_once()
        assert "Whitelist:" in str(i.followup.send.call_args[0][0])


class TestWhitelistAdd:
    @pytest.mark.asyncio
    async def test_add_success(self):
        with patch("bot.commands.whitelist.get_profile", new_callable=AsyncMock, return_value=("uuid", "Steve")), patch(
            "bot.commands.whitelist.add_to_cache", new_callable=AsyncMock
        ):
            bot = make_bot()
            bot.db_pool, _ = make_db_pool()
            cog = WhitelistCommands(bot)
            i = make_interaction()
            await cog.whitelist_add.callback(cog, i, "Steve")
            bot.minecraft_rcon.whitelist_add.assert_awaited_once_with("Steve")

    @pytest.mark.asyncio
    async def test_add_invalid_username(self):
        bot = make_bot()
        bot.db_pool, _ = make_db_pool()
        cog = WhitelistCommands(bot)
        i = make_interaction()
        await cog.whitelist_add.callback(cog, i, "ab")
        bot.minecraft_rcon.whitelist_add.assert_not_awaited()
        assert "Invalid" in str(i.followup.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_add_no_rcon(self):
        bot = make_bot()
        bot.minecraft_rcon = None
        bot.db_pool, _ = make_db_pool()
        cog = WhitelistCommands(bot)
        i = make_interaction()
        await cog.whitelist_add.callback(cog, i, "Steve")
        assert "not configured" in str(i.followup.send.call_args[0][0]).lower()


class TestWhitelistRemove:
    @pytest.mark.asyncio
    async def test_remove_success(self):
        with patch("bot.commands.whitelist.remove_from_cache", new_callable=AsyncMock):
            bot = make_bot()
            bot.db_pool, _ = make_db_pool()
            cog = WhitelistCommands(bot)
            i = make_interaction()
            await cog.whitelist_remove.callback(cog, i, "Steve")
            bot.minecraft_rcon.whitelist_remove.assert_awaited_once_with("Steve")

    @pytest.mark.asyncio
    async def test_remove_invalid_username(self):
        bot = make_bot()
        bot.db_pool, _ = make_db_pool()
        cog = WhitelistCommands(bot)
        i = make_interaction()
        await cog.whitelist_remove.callback(cog, i, "x")
        bot.minecraft_rcon.whitelist_remove.assert_not_awaited()
        assert "Invalid" in str(i.followup.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_remove_no_rcon(self):
        bot = make_bot()
        bot.minecraft_rcon = None
        bot.db_pool, _ = make_db_pool()
        cog = WhitelistCommands(bot)
        i = make_interaction()
        await cog.whitelist_remove.callback(cog, i, "Steve")
        assert "not configured" in str(i.followup.send.call_args[0][0]).lower()


class TestWhitelistSync:
    @pytest.mark.asyncio
    async def test_sync_success(self):
        with patch(
            "bot.commands.whitelist.sync_from_rcon",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "bot.commands.whitelist.get_cached_usernames",
            new_callable=AsyncMock,
            return_value=["Steve", "Alex"],
        ):
            bot = make_bot()
            bot.db_pool, _ = make_db_pool()
            cog = WhitelistCommands(bot)
            i = make_interaction()
            await cog.whitelist_sync.callback(cog, i)
            assert "Synced" in str(i.followup.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_sync_failure(self):
        with patch(
            "bot.commands.whitelist.sync_from_rcon",
            new_callable=AsyncMock,
            return_value=False,
        ):
            bot = make_bot()
            bot.db_pool, _ = make_db_pool()
            cog = WhitelistCommands(bot)
            i = make_interaction()
            await cog.whitelist_sync.callback(cog, i)
            assert "Failed" in str(i.followup.send.call_args[0][0])

    @pytest.mark.asyncio
    async def test_sync_no_rcon(self):
        bot = make_bot()
        bot.minecraft_rcon = None
        bot.db_pool, _ = make_db_pool()
        cog = WhitelistCommands(bot)
        i = make_interaction()
        await cog.whitelist_sync.callback(cog, i)
        assert "not configured" in str(i.followup.send.call_args[0][0]).lower()
