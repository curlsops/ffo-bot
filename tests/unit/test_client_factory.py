import logging
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest

from bot.client import FFOBot, FFOShardedBot, _parse_discord_shard_ids, create_ffo_bot


def test_parse_discord_shard_ids():
    assert _parse_discord_shard_ids(None) is None
    assert _parse_discord_shard_ids("") is None
    assert _parse_discord_shard_ids("  ") is None
    assert _parse_discord_shard_ids("0, 1,2") == [0, 1, 2]


def test_create_ffo_bot(mock_settings):
    mock_settings.discord_sharding_enabled = False
    assert isinstance(create_ffo_bot(mock_settings), FFOBot)
    mock_settings.discord_sharding_enabled = True
    assert isinstance(create_ffo_bot(mock_settings), FFOShardedBot)


@pytest.mark.asyncio
async def test_on_ready_multi_shard_defers_until_all_ready(mock_settings):
    bot = FFOShardedBot(mock_settings)
    bot.shard_count = 2
    with patch("bot.client.logger") as log:
        with patch.object(bot, "is_ready", return_value=False):
            await bot.on_ready()
    log.info.assert_not_called()


@pytest.mark.asyncio
async def test_on_ready_autosharded_single_shard_does_not_defer(mock_settings):
    mock_settings.sync_commands_on_boot = True
    mock_settings.clear_commands_on_boot = True
    bot = FFOShardedBot(mock_settings)
    bot.shard_count = 1
    mock_http = MagicMock()
    mock_http.bulk_upsert_global_commands = AsyncMock()
    mock_conn = MagicMock(http=mock_http)
    with (
        patch.object(discord.Client, "user", PropertyMock(return_value=MagicMock(id=123))),
        patch.object(discord.Client, "guilds", PropertyMock(return_value=[])),
        patch.object(bot, "_register_server", new_callable=AsyncMock),
        patch.object(bot, "_connection", mock_conn),
        patch.object(bot.tree, "copy_global_to"),
        patch.object(bot.tree, "sync", new_callable=AsyncMock),
    ):
        await bot.on_ready()
    mock_http.bulk_upsert_global_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_shard_ready_logs_when_multi_shard(mock_settings, caplog):
    bot = FFOShardedBot(mock_settings)
    bot.shard_count = 2
    caplog.set_level(logging.INFO, logger="bot.client")
    await bot.on_shard_ready(3)
    assert "Shard 3 connected" in caplog.text


@pytest.mark.asyncio
async def test_on_shard_ready_skips_log_when_single_shard(mock_settings):
    bot = FFOShardedBot(mock_settings)
    bot.shard_count = 1
    with patch("bot.client.logger") as log:
        await bot.on_shard_ready(0)
    log.info.assert_not_called()


@pytest.mark.asyncio
async def test_ffoshardedbot_close_calls_super_close(mock_settings):
    bot = FFOShardedBot(mock_settings)
    with patch.object(bot, "_drain_message_queue", new_callable=AsyncMock):
        with patch(
            "discord.ext.commands.AutoShardedBot.close", new_callable=AsyncMock
        ) as mock_super:
            await bot.close()
    mock_super.assert_awaited_once()
