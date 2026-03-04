from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.pagination import (
    DISCORD_LIMIT,
    PER_PAGE,
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
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()
        await view._prev_callback(interaction)
        interaction.response.edit_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_next_at_max_no_edit(self):
        view = ListPaginatedView(["a"], "H", _fmt)
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()
        await view._next_callback(interaction)
        interaction.response.edit_message.assert_not_awaited()
