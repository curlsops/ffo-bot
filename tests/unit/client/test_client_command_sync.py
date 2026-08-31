from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.client import sync_commands


class TestSyncCommands:
    @pytest.mark.asyncio
    async def test_clears_and_syncs_each_guild_when_clear_on_boot(self):
        tree = MagicMock()
        tree.copy_global_to = MagicMock()
        tree.sync = AsyncMock()
        http = MagicMock()
        http.bulk_upsert_global_commands = AsyncMock()
        http.bulk_upsert_guild_commands = AsyncMock()
        guilds = [MagicMock(id=111), MagicMock(id=222)]

        result = await sync_commands(tree, http, 999, guilds, clear_on_boot=True)

        http.bulk_upsert_global_commands.assert_awaited_once_with(999, [])
        assert http.bulk_upsert_guild_commands.await_count == 2
        http.bulk_upsert_guild_commands.assert_any_await(999, 111, [])
        http.bulk_upsert_guild_commands.assert_any_await(999, 222, [])
        assert tree.copy_global_to.call_count == 2
        assert tree.sync.await_count == 2
        assert result == 2

    @pytest.mark.asyncio
    async def test_skips_clearing_when_clear_on_boot_false(self):
        tree = MagicMock()
        tree.copy_global_to = MagicMock()
        tree.sync = AsyncMock()
        http = MagicMock()
        http.bulk_upsert_global_commands = AsyncMock()
        http.bulk_upsert_guild_commands = AsyncMock()
        guilds = [MagicMock(id=111)]

        result = await sync_commands(tree, http, 999, guilds, clear_on_boot=False)

        http.bulk_upsert_global_commands.assert_not_awaited()
        http.bulk_upsert_guild_commands.assert_not_awaited()
        tree.copy_global_to.assert_called_once_with(guild=guilds[0])
        tree.sync.assert_awaited_once_with(guild=guilds[0])
        assert result == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_global_sync_when_no_guilds(self):
        tree = MagicMock()
        tree.sync = AsyncMock()
        http = MagicMock()
        http.bulk_upsert_global_commands = AsyncMock()

        result = await sync_commands(tree, http, 999, [], clear_on_boot=True)

        http.bulk_upsert_global_commands.assert_awaited_once_with(999, [])
        tree.sync.assert_awaited_once_with()
        assert result == 0
