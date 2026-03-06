from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.pagination import (
    PER_PAGE,
    ListPaginatedView,
    paginate_by_char_limit,
    truncate_for_discord,
)


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

    def test_truncate_when_over_limit(self):
        short = "hello"
        assert truncate_for_discord(short) == short
        long_content = "x" * 2500
        result = truncate_for_discord(long_content)
        assert len(result) <= 2000
        assert result.endswith("...(truncated)")


class TestPaginateByCharLimit:
    def test_empty_returns_empty(self):
        assert paginate_by_char_limit([], 100) == []

    def test_single_block(self):
        assert paginate_by_char_limit(["abc"], 10) == ["abc"]

    def test_splits_when_over_limit(self):
        blocks = ["a" * 5, "b" * 5, "c" * 5]
        pages = paginate_by_char_limit(blocks, 8)
        assert len(pages) == 3
        assert pages[0] == "aaaaa"
        assert pages[1] == "bbbbb"
        assert pages[2] == "ccccc"

    def test_packs_blocks_until_limit(self):
        blocks = ["a" * 3, "b" * 3, "c" * 3]
        pages = paginate_by_char_limit(blocks, 8)
        assert len(pages) == 2
        assert pages[0] == "aaabbb"
        assert pages[1] == "ccc"
