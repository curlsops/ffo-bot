import pytest

from bot.utils.pagination import (
    DISCORD_LIMIT,
    PER_PAGE,
    ListPaginatedView,
    paginate_by_char_limit,
    truncate_for_discord,
)


def _fmt(x):
    return f"• {x}"


class TestPaginateByCharLimitParametrized:
    @pytest.mark.parametrize("limit", [1, 5, 10, 50, 100, 500, 1000])
    def test_empty_returns_empty(self, limit):
        assert paginate_by_char_limit([], limit) == []

    @pytest.mark.parametrize("block_len,limit", [(1, 10), (5, 50), (10, 100), (50, 100)])
    def test_single_block_under_limit(self, block_len, limit):
        blocks = ["a" * block_len]
        assert paginate_by_char_limit(blocks, limit) == ["a" * block_len]

    @pytest.mark.parametrize("limit", [5, 6, 7, 8, 9, 10])
    def test_blocks_combined_until_limit(self, limit):
        blocks = ["a" * 3, "b" * 3, "c" * 3]
        pages = paginate_by_char_limit(blocks, limit)
        assert pages
        for p in pages:
            assert len(p) <= limit

    @pytest.mark.parametrize("n_blocks", [2, 3, 5, 10])
    def test_blocks_each_over_limit(self, n_blocks):
        blocks = ["x" * 10 for _ in range(n_blocks)]
        pages = paginate_by_char_limit(blocks, 5)
        assert len(pages) == n_blocks
        assert all(p == "x" * 10 for p in pages)

    @pytest.mark.parametrize("limit", [1, 2, 3, 4, 5])
    def test_exactly_fits_limit(self, limit):
        blocks = ["a" * limit]
        assert paginate_by_char_limit(blocks, limit) == ["a" * limit]


class TestTruncateForDiscordParametrized:
    @pytest.mark.parametrize("length", [0, 1, 100, 500, 1000, DISCORD_LIMIT - 1, DISCORD_LIMIT])
    def test_under_limit_unchanged(self, length):
        content = "x" * length
        assert truncate_for_discord(content) == content

    @pytest.mark.parametrize("over_by", [1, 10, 20, 50, 100, 500, 1000])
    def test_over_limit_truncates(self, over_by):
        content = "a" * (DISCORD_LIMIT + over_by)
        result = truncate_for_discord(content)
        assert len(result) <= DISCORD_LIMIT
        assert result.endswith("...(truncated)")

    @pytest.mark.parametrize("content", ["", "x", "hello", "a" * 100])
    def test_short_content_unchanged(self, content):
        assert truncate_for_discord(content) == content


class TestListPaginatedViewParametrized:
    @pytest.mark.parametrize("num_rows", [0, 1, 5, PER_PAGE, PER_PAGE + 1, PER_PAGE * 2])
    def test_max_page(self, num_rows):
        rows = list(range(num_rows))
        view = ListPaginatedView(rows, "H", _fmt)
        expected = max(0, (num_rows - 1) // PER_PAGE)
        assert view._max_page == expected

    @pytest.mark.parametrize("per_page", [1, 5, 10, 20])
    def test_per_page_override(self, per_page):
        rows = list(range(per_page * 2))
        view = ListPaginatedView(rows, "H", _fmt, per_page=per_page)
        assert view.per_page == per_page
        assert view._max_page == 1

    @pytest.mark.parametrize("header", ["", "Header", "**Bold**", "A" * 50])
    def test_header_in_output(self, header):
        view = ListPaginatedView(["a"], header, _fmt)
        assert header in view._format_page()
