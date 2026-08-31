from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.app_commands import AppCommandError

from tests.helpers import mock_interaction


class TestMetricsCommandTreeInteractionCheck:
    @pytest.mark.asyncio
    async def test_allows_when_rate_limit_not_exceeded(self, bot):
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
        tree = bot.tree

        i = mock_interaction(guild_id=12345)
        i.data = {"type": 1, "name": "test", "options": []}

        with patch.object(
            tree, "_get_app_command_options", return_value=(MagicMock(qualified_name="test"), [])
        ):
            result = await tree.interaction_check(i)

        assert result is True
        bot.rate_limiter.check_rate_limit.assert_awaited_once_with(i.user.id, 12345)
        i.response.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_denies_and_replies_when_rate_limited_without_notify(self, bot):
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "Rate limited"))
        bot.settings.feature_notify_rate_limit = False
        bot.notifier = MagicMock(notify_rate_limit_hit=AsyncMock())
        tree = bot.tree

        i = mock_interaction(guild_id=123, user_id=456)
        i.data = {"type": 1, "name": "test", "options": []}
        i.response.is_done.return_value = False

        with patch.object(
            tree, "_get_app_command_options", return_value=(MagicMock(qualified_name="test"), [])
        ):
            result = await tree.interaction_check(i)

        assert result is False
        bot.notifier.notify_rate_limit_hit.assert_not_awaited()
        i.response.send_message.assert_awaited_once_with("Rate limited", ephemeral=True)

    @pytest.mark.asyncio
    async def test_denies_and_notifies_via_followup_when_response_done(self, bot):
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "Slow down"))
        bot.settings.feature_notify_rate_limit = True
        bot.notifier = MagicMock(notify_rate_limit_hit=AsyncMock())
        tree = bot.tree

        i = mock_interaction(guild_id=1, user_id=2)
        i.data = {"type": 1, "name": "cmd", "options": []}
        i.response.is_done.return_value = True

        with patch.object(
            tree, "_get_app_command_options", return_value=(MagicMock(qualified_name="cmd"), [])
        ):
            result = await tree.interaction_check(i)

        assert result is False
        bot.notifier.notify_rate_limit_hit.assert_awaited_once_with(1, 2, "Slow down", "cmd")
        i.followup.send.assert_awaited_once_with("Slow down", ephemeral=True)

    @pytest.mark.asyncio
    async def test_allows_without_checking_when_no_rate_limiter(self, bot):
        bot.rate_limiter = None
        tree = bot.tree

        i = mock_interaction(guild_id=1)

        result = await tree.interaction_check(i)

        assert result is True

    @pytest.mark.asyncio
    async def test_allows_without_checking_when_no_guild_id(self, bot):
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock()
        tree = bot.tree

        i = mock_interaction(guild_id=None, guild=False)

        result = await tree.interaction_check(i)

        assert result is True
        bot.rate_limiter.check_rate_limit.assert_not_awaited()


class TestMetricsCommandTreeCall:
    @pytest.mark.asyncio
    async def test_call_records_metrics_on_success(self, bot):
        bot.metrics = MagicMock()
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
        tree = bot.tree
        mock_cmd = MagicMock(qualified_name="test")
        mock_cmd._invoke_with_namespace = AsyncMock()

        i = mock_interaction(guild_id=12345)
        i.data = {"type": 1, "name": "test", "options": []}
        i.command_failed = False
        i.type = MagicMock()

        with patch.object(tree, "_get_app_command_options", return_value=(mock_cmd, [])):
            await tree._call(i)

        mock_cmd._invoke_with_namespace.assert_awaited_once()
        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="test", server_id="12345", status="success"
        )
        bot.metrics.command_duration.labels.assert_called_once_with(command_name="test")
        bot.metrics.commands_executed.labels.return_value.inc.assert_called_once()
        bot.metrics.command_duration.labels.return_value.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_rate_limited_stops_before_command_runs(self, bot):
        bot.metrics = MagicMock()
        bot.rate_limiter = MagicMock()
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "Rate limited"))
        bot.settings.feature_notify_rate_limit = False
        tree = bot.tree
        mock_cmd = MagicMock(qualified_name="test")
        mock_cmd._invoke_with_namespace = AsyncMock()

        i = mock_interaction(guild_id=123, user_id=456)
        i.data = {"type": 1, "name": "test", "options": []}
        i.response.is_done.return_value = False

        with patch.object(tree, "_get_app_command_options", return_value=(mock_cmd, [])):
            await tree._call(i)

        mock_cmd._invoke_with_namespace.assert_not_awaited()
        i.response.send_message.assert_awaited_once_with("Rate limited", ephemeral=True)
        assert i.command_failed is True
        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="test", server_id="123", status="error"
        )

    @pytest.mark.asyncio
    async def test_call_records_error_status_when_command_raises(self, bot):
        bot.metrics = MagicMock()
        bot.rate_limiter = None
        tree = bot.tree
        mock_cmd = MagicMock(qualified_name="failing_cmd")
        mock_cmd._invoke_with_namespace = AsyncMock(side_effect=AppCommandError("boom"))
        mock_cmd._invoke_error_handlers = AsyncMock()

        i = mock_interaction(guild_id=999)
        i.data = {"type": 1, "name": "failing_cmd", "options": []}
        i.command_failed = False
        i.type = MagicMock()

        with patch.object(tree, "_get_app_command_options", return_value=(mock_cmd, [])):
            await tree._call(i)

        mock_cmd._invoke_error_handlers.assert_awaited_once()
        assert i.command_failed is True
        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="failing_cmd", server_id="999", status="error"
        )

    @pytest.mark.asyncio
    async def test_call_context_menu_uses_name(self, bot):
        bot.metrics = MagicMock()
        bot.rate_limiter = None
        tree = bot.tree

        i = mock_interaction(guild_id=1, channel_id=None)
        i.data = {"type": 2, "name": "Copy ID"}
        i.command_failed = False

        with patch.object(tree, "_call_context_menu", new_callable=AsyncMock) as mock_ctx:
            await tree._call(i)

        mock_ctx.assert_awaited_once_with(i, i.data, 2)
        bot.metrics.commands_executed.labels.assert_called_once_with(
            command_name="Copy ID", server_id="1", status="success"
        )

    @pytest.mark.asyncio
    async def test_call_skips_metrics_when_none(self, bot):
        bot.metrics = None
        bot.rate_limiter = None
        tree = bot.tree

        i = mock_interaction(guild_id=None, guild=False, channel_id=None)
        i.data = {"type": 2, "name": "Copy ID"}
        i.command_failed = False

        with patch.object(tree, "_call_context_menu", new_callable=AsyncMock):
            await tree._call(i)
