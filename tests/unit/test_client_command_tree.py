from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMetricsCommandTree:
    @pytest.mark.asyncio
    async def test_call_records_metrics_on_success(self, bot):
        bot.metrics = MagicMock()
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
        tree = bot.tree
        mock_cmd = MagicMock(qualified_name="test")

        i = MagicMock()
        i.data = {"type": 1, "name": "test", "options": []}
        i.guild_id = 12345
        i.command_failed = False

        with patch.object(tree, "_get_app_command_options", return_value=(mock_cmd, [])):
            with patch("bot.client.app_commands.CommandTree._call", new_callable=AsyncMock):
                await tree._call(i)

        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="test", server_id="12345", status="success"
        )
        bot.metrics.command_duration.labels.assert_called_once_with(command_name="test")
        bot.metrics.commands_executed.labels.return_value.inc.assert_called_once()
        bot.metrics.command_duration.labels.return_value.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_records_error_status_when_failed(self, bot):
        bot.metrics = MagicMock()
        tree = bot.tree
        mock_cmd = MagicMock(qualified_name="failing_cmd")

        i = MagicMock()
        i.data = {"type": 1, "name": "failing_cmd", "options": []}
        i.guild_id = 999
        i.command_failed = True

        with patch.object(tree, "_get_app_command_options", return_value=(mock_cmd, [])):
            with patch("bot.client.app_commands.CommandTree._call", new_callable=AsyncMock):
                await tree._call(i)

        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="failing_cmd", server_id="999", status="error"
        )

    @pytest.mark.asyncio
    async def test_call_extracts_command_name_from_data(self, bot):
        bot.metrics = MagicMock()
        tree = bot.tree

        mock_cmd = MagicMock(qualified_name="faq_list")
        i = MagicMock()
        i.data = {"type": 1, "options": []}
        i.guild_id = 1
        i.command_failed = False

        with patch.object(tree, "_get_app_command_options", return_value=(mock_cmd, [])):
            with patch("bot.client.app_commands.CommandTree._call", new_callable=AsyncMock):
                await tree._call(i)

        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="faq_list", server_id="1", status="success"
        )
        bot.metrics.command_duration.labels.assert_called_once_with(command_name="faq_list")

    @pytest.mark.asyncio
    async def test_call_context_menu_uses_name(self, bot):
        bot.metrics = MagicMock()
        tree = bot.tree

        i = MagicMock()
        i.data = {"type": 2, "name": "Copy ID"}
        i.guild_id = 1
        i.command_failed = False

        with patch("bot.client.app_commands.CommandTree._call", new_callable=AsyncMock):
            await tree._call(i)

        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="Copy ID", server_id="1", status="success"
        )

    @pytest.mark.asyncio
    async def test_call_skips_metrics_when_none(self, bot):
        bot.metrics = None
        tree = bot.tree

        i = MagicMock()
        i.data = {"type": 2, "name": "Copy ID"}
        i.guild_id = None

        with patch("bot.client.app_commands.CommandTree._call", new_callable=AsyncMock):
            await tree._call(i)

    @pytest.mark.asyncio
    async def test_call_rate_limited_returns_early(self, bot):
        bot.metrics = MagicMock()
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "Rate limited"))
        bot.settings.feature_notify_rate_limit = False
        tree = bot.tree

        i = MagicMock()
        i.data = {"type": 1, "name": "test", "options": []}
        i.guild_id = 123
        i.user = MagicMock(id=456)
        i.response.is_done.return_value = False
        i.response.send_message = AsyncMock()
        i.followup.send = AsyncMock()

        with patch.object(
            tree, "_get_app_command_options", return_value=(MagicMock(qualified_name="test"), [])
        ):
            with patch(
                "bot.client.app_commands.CommandTree._call", new_callable=AsyncMock
            ) as mock_super:
                await tree._call(i)

        mock_super.assert_not_called()
        i.response.send_message.assert_awaited_once_with("Rate limited", ephemeral=True)
        assert i.command_failed is True

    @pytest.mark.asyncio
    async def test_call_rate_limited_with_notify_uses_followup_when_done(self, bot):
        bot.metrics = MagicMock()
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "Slow down"))
        bot.settings.feature_notify_rate_limit = True
        bot.notifier = MagicMock(notify_rate_limit_hit=AsyncMock())
        tree = bot.tree

        i = MagicMock()
        i.data = {"type": 1, "name": "cmd", "options": []}
        i.guild_id = 1
        i.user = MagicMock(id=2)
        i.response.is_done.return_value = True
        i.followup.send = AsyncMock()

        with patch.object(
            tree, "_get_app_command_options", return_value=(MagicMock(qualified_name="cmd"), [])
        ):
            with patch("bot.client.app_commands.CommandTree._call", new_callable=AsyncMock):
                await tree._call(i)

        bot.notifier.notify_rate_limit_hit.assert_awaited_once_with(1, 2, "Slow down", "cmd")
        i.followup.send.assert_awaited_once_with("Slow down", ephemeral=True)
