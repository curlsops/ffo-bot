import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers import db_pool_with_conn


class TestFFOBotExtensions:
    @pytest.mark.asyncio
    async def test_load_extensions_success(self, bot):
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            assert mock_load.call_count >= 10  # base + optional (quotebook, whitelist, faq)

    @pytest.mark.asyncio
    async def test_load_extensions_handles_failure(self, bot, caplog):
        async def fail_first(*args):
            raise Exception("Load failed")

        caplog.set_level(logging.ERROR, logger="bot.client")
        with patch.object(bot, "load_extension", side_effect=fail_first):
            await bot._load_extensions()
        assert "Failed to load extension" in caplog.text

    @pytest.mark.asyncio
    async def test_load_extensions_with_quotebook(self, mock_settings):
        mock_settings.feature_quotebook = True
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            assert any("quotebook" in c.args[0] for c in mock_load.call_args_list)

    @pytest.mark.asyncio
    async def test_load_extensions_with_whitelist(self, mock_settings):
        mock_settings.feature_minecraft_whitelist = True
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            loaded = [c.args[0] for c in mock_load.call_args_list]
            assert any(ext == "bot.commands.whitelist" for ext in loaded)
            assert any(ext == "bot.tasks.whitelist_cache_reconcile" for ext in loaded)

    @pytest.mark.asyncio
    async def test_load_extensions_whitelist_skips_auto_reconcile_when_interval_zero(
        self, mock_settings
    ):
        mock_settings.feature_minecraft_whitelist = True
        mock_settings.whitelist_cache_reconcile_interval_hours = 0
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            loaded = [c.args[0] for c in mock_load.call_args_list]
            assert "bot.tasks.whitelist_cache_reconcile" not in loaded

    @pytest.mark.asyncio
    async def test_load_extensions_with_faq(self, mock_settings):
        mock_settings.feature_faq = True
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            assert any("faq" in c.args[0] for c in mock_load.call_args_list)

    @pytest.mark.asyncio
    async def test_load_extensions_with_music(self, mock_settings):
        mock_settings.feature_music = True
        from bot.client import FFOBot

        bot = FFOBot(mock_settings)
        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_extensions()
            assert any("music" in c.args[0] for c in mock_load.call_args_list)

    @pytest.mark.asyncio
    async def test_load_extensions_multiple_failures(self, bot, caplog):
        caplog.set_level(logging.WARNING, logger="bot.client")

        async def fail_all(*args):
            raise Exception("load failed")

        with patch.object(bot, "load_extension", side_effect=fail_all):
            await bot._load_extensions()
        assert caplog.text.count("load failed") >= 1


class TestFFOBotPersistentViews:
    @pytest.mark.asyncio
    async def test_register_persistent_views_enabled(self, bot):
        import uuid

        bot.settings.feature_giveaways = True
        gid, mid = uuid.uuid4(), 12345
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"id": gid, "message_id": mid, "entry_count": 0}])
        conn.fetchval = AsyncMock(return_value=0)
        bot.db_pool = db_pool_with_conn(conn)
        with patch("bot.commands.giveaway.GiveawayView"):
            with patch.object(bot, "add_view") as mock_add:
                await bot._register_persistent_views()
                assert mock_add.call_count == 2  # CloseGiveawayThreadView + GiveawayView
                giveaways_calls = [c for c in mock_add.call_args_list if len(c.kwargs) > 0]
                assert giveaways_calls[0].kwargs["message_id"] == mid

    @pytest.mark.asyncio
    async def test_register_persistent_views_anonymous_post(self, bot):
        from bot.commands.anonymous import AnonymousPostButtonView

        bot.settings.feature_anonymous_post = True
        bot.settings.feature_giveaways = False
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"message_id": 99, "post_channel_id": 42}])
        bot.db_pool = db_pool_with_conn(conn)
        with patch.object(bot, "add_view") as mock_add:
            await bot._register_persistent_views()
            mock_add.assert_called_once()
            call = mock_add.call_args_list[0]
            assert call.kwargs.get("message_id") == 99
            view = call.args[0]
            assert isinstance(view, AnonymousPostButtonView)
            assert view.post_channel_id == 42

    @pytest.mark.asyncio
    async def test_register_persistent_views_disabled(self, bot):
        bot.settings.feature_giveaways = False
        with patch.object(bot, "add_view") as mock_add:
            await bot._register_persistent_views()
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_persistent_views_no_active(self, bot):
        bot.settings.feature_giveaways = True
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        bot.db_pool = db_pool_with_conn(conn)
        with patch.object(bot, "add_view") as mock_add:
            await bot._register_persistent_views()
            mock_add.assert_called_once()  # CloseGiveawayThreadView only

    @pytest.mark.asyncio
    async def test_register_persistent_views_multiple(self, bot):
        import uuid

        bot.settings.feature_giveaways = True
        rows = [
            {"id": uuid.uuid4(), "message_id": 111, "entry_count": 0},
            {"id": uuid.uuid4(), "message_id": 222, "entry_count": 5},
            {"id": uuid.uuid4(), "message_id": 333, "entry_count": 1},
        ]
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.fetchval = AsyncMock(return_value=0)
        bot.db_pool = db_pool_with_conn(conn)
        with patch("bot.commands.giveaway.GiveawayView"):
            with patch.object(bot, "add_view") as mock_add:
                await bot._register_persistent_views()
                assert mock_add.call_count == 4  # CloseGiveawayThreadView + 3 GiveawayView
                message_ids = [
                    c.kwargs["message_id"]
                    for c in mock_add.call_args_list
                    if "message_id" in c.kwargs
                ]
                assert message_ids == [111, 222, 333]

    @pytest.mark.asyncio
    async def test_register_persistent_views_acquire_raises(self, bot):
        bot.settings.feature_giveaways = True
        bot.db_pool = MagicMock()
        bot.db_pool.acquire = MagicMock(side_effect=Exception("DB"))
        with pytest.raises(Exception, match="DB"):
            await bot._register_persistent_views()
