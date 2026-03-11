from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.pagination import (
    DISCORD_LIMIT,
    PER_PAGE,
    EmbedListPaginatedView,
    EmbedPaginatedView,
    ListPaginatedView,
    truncate_for_discord,
)


def _fmt(x):
    return f"• {x}"


class TestTruncateForDiscord:
    def test_short_content_unchanged(self):
        for length in [0, 1, 100, DISCORD_LIMIT - 1, DISCORD_LIMIT]:
            content = "x" * length
            assert truncate_for_discord(content) == content

    def test_over_limit_truncates(self):
        content = "x" * (DISCORD_LIMIT + 100)
        result = truncate_for_discord(content)
        assert len(result) <= DISCORD_LIMIT
        assert result.endswith("...(truncated)")

    @pytest.mark.parametrize("over_by", [1, 20, 100, 500, 1000])
    def test_over_limit_truncates_various(self, over_by):
        content = "a" * (DISCORD_LIMIT + over_by)
        result = truncate_for_discord(content)
        assert len(result) <= DISCORD_LIMIT
        assert "...(truncated)" in result


class TestListPaginatedViewExtended:
    @pytest.mark.parametrize("num_rows", [0, 1, PER_PAGE, PER_PAGE + 1, PER_PAGE * 2, PER_PAGE * 3])
    def test_max_page_calculation(self, num_rows):
        rows = list(range(num_rows))
        view = ListPaginatedView(rows, "Header", _fmt)
        expected_max = max(0, (num_rows - 1) // PER_PAGE)
        assert view._max_page == expected_max

    def test_empty_rows(self):
        view = ListPaginatedView([], "Empty", _fmt)
        assert view._max_page == 0
        assert "Empty" in view._format_page()

    def test_single_row(self):
        view = ListPaginatedView(["only"], "One", _fmt)
        assert view._format_page() == "One\n\n• only"

    @pytest.mark.parametrize("page", [0, 1, 2])
    def test_page_slice(self, page):
        rows = [f"r{i}" for i in range(PER_PAGE * 3)]
        view = ListPaginatedView(rows, "H", _fmt)
        view.page = page
        content = view._format_page()
        start = page * PER_PAGE
        expected_first = f"r{start}"
        assert f"• {expected_first}" in content

    @pytest.mark.asyncio
    async def test_prev_at_zero_no_edit(self):
        view = ListPaginatedView(["a"], "H", _fmt)
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._prev_callback(i)
        i.response.edit_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_next_at_max_no_edit(self):
        view = ListPaginatedView(["a"], "H", _fmt)
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._next_callback(i)
        i.response.edit_message.assert_not_awaited()


class TestEmbedPaginatedView:
    def test_format_page_with_footer_template(self):
        view = EmbedPaginatedView(["p1", "p2"], title="T", footer_template="Page {page}/{total}")
        embed = view._format_page()
        assert embed.title == "T"
        assert embed.description == "p1"
        assert "Page 1/2" in embed.footer.text

    def test_format_page_with_static_footer(self):
        view = EmbedPaginatedView(["x"], title="X", footer="Static footer")
        embed = view._format_page()
        assert embed.footer.text == "Static footer"

    @pytest.mark.asyncio
    async def test_prev_callback_advances(self):
        view = EmbedPaginatedView(["a", "b"], title="T")
        view.page = 1
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._prev_callback(i)
        assert view.page == 0
        i.response.edit_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_next_callback_advances(self):
        view = EmbedPaginatedView(["a", "b"], title="T")
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._next_callback(i)
        assert view.page == 1
        i.response.edit_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prev_at_zero_no_op(self):
        view = EmbedPaginatedView(["a"], title="T")
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._prev_callback(i)
        i.response.edit_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_next_at_max_no_op(self):
        view = EmbedPaginatedView(["a"], title="T")
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._next_callback(i)
        i.response.edit_message.assert_not_awaited()


class TestEmbedListPaginatedView:
    def test_format_page(self):
        view = EmbedListPaginatedView([1, 2, 3], lambda r: f"• {r}", title="List")
        embed = view._format_page()
        assert embed.title == "List"
        assert "• 1" in embed.description and "• 2" in embed.description

    @pytest.mark.asyncio
    async def test_prev_next_callbacks(self):
        view = EmbedListPaginatedView(list(range(15)), lambda r: str(r), title="X", per_page=5)
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._next_callback(i)
        assert view.page == 1
        await view._prev_callback(i)
        assert view.page == 0

    @pytest.mark.asyncio
    async def test_prev_at_zero_no_op(self):
        view = EmbedListPaginatedView([1, 2], lambda r: str(r), title="X")
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._prev_callback(i)
        assert view.page == 0
        i.response.edit_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_next_at_max_no_op(self):
        view = EmbedListPaginatedView([1, 2], lambda r: str(r), title="X")
        view.page = 1
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view._next_callback(i)
        assert view.page == 1
        i.response.edit_message.assert_not_awaited()
