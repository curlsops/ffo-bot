from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.pagination import PER_PAGE, ListPaginatedView


def _fmt(x):
    return f"• {x}"


class TestListPaginatedView:
    def test_single_page_format(self):
        rows = ["a", "b", "c"]
        view = ListPaginatedView(rows, "**Header:**", _fmt)
        assert view._format_page() == "**Header:**\n\n• a\n• b\n• c"
        assert view._max_page == 0

    def test_multi_page_format(self):
        rows = [f"item{i}" for i in range(PER_PAGE + 5)]
        view = ListPaginatedView(rows, "**List:**", _fmt)
        assert view._max_page == 1
        assert "• item0" in view._format_page()
        view.page = 1
        assert "• item10" in view._format_page()

    @pytest.mark.asyncio
    async def test_next_callback_advances_page(self):
        rows = [f"x{i}" for i in range(PER_PAGE + 3)]
        view = ListPaginatedView(rows, "**Items:**", _fmt)
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await view._next_callback(interaction)

        assert view.page == 1
        interaction.response.edit_message.assert_awaited_once()
        call_content = interaction.response.edit_message.call_args.kwargs.get("content", "")
        assert "• x10" in call_content

    @pytest.mark.asyncio
    async def test_prev_callback_goes_back(self):
        rows = [f"y{i}" for i in range(PER_PAGE + 2)]
        view = ListPaginatedView(rows, "**List:**", _fmt)
        view.page = 1
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await view._prev_callback(interaction)

        assert view.page == 0
        interaction.response.edit_message.assert_awaited_once()
        call_content = interaction.response.edit_message.call_args.kwargs.get("content", "")
        assert "• y0" in call_content

    @pytest.mark.asyncio
    async def test_prev_at_page_zero_no_op(self):
        rows = ["a", "b"]
        view = ListPaginatedView(rows, "**X:**", _fmt)
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await view._prev_callback(interaction)

        assert view.page == 0
        interaction.response.edit_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_next_at_max_page_no_op(self):
        rows = ["a", "b"]
        view = ListPaginatedView(rows, "**X:**", _fmt)
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()

        await view._next_callback(interaction)

        assert view.page == 0
        interaction.response.edit_message.assert_not_awaited()
