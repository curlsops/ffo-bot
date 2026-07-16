from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from bot.services.tidal import (
    TIDAL_ALBUM_PATTERN,
    TIDAL_TRACK_PATTERN,
)
from bot.services.tidal import _fetch_catalog_from_api as tidal_fetch_catalog_from_api
from bot.services.tidal import _sample_catalog_queries as tidal_sample_catalog_queries
from bot.services.tidal import (
    tidal_album_to_search_queries,
    tidal_mix_catalog_start,
    tidal_mix_to_search_queries,
    tidal_playlist_catalog_start,
    tidal_playlist_to_search_queries,
    tidal_url_to_search_query,
)

TIDAL_TRACK_URL = "https://tidal.com/track/110653480/u"
TIDAL_ALBUM_URL = "https://tidal.com/album/476908869/u"
TIDAL_TRACK_TITLE = "Excision & Dion Timmer - Time Stood Still"
TIDAL_PLAYLIST_URL = "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd"
TIDAL_MIX_URL = "https://tidal.com/browse/mix/3f4f1385-aa86-46e5-a6ad-cb18248be3cd"


class TestTidalSampleCatalogQueries:
    def test_empty_returns_empty(self):
        assert tidal_sample_catalog_queries([]) == []

    @pytest.mark.asyncio
    async def test_fetch_catalog_zero_cap_skips_http(self):
        mock_session = MagicMock()
        result = await tidal_fetch_catalog_from_api(
            mock_session, "playlists/x/tracks", max_tracks=0
        )
        assert result is None
        mock_session.get.assert_not_called()

    def test_returns_prefix_in_order_capped_by_resolve_sample(self):
        queries = [f"q{i}" for i in range(8)]
        with patch("bot.services.tidal.TIDAL_PLAYLIST_RESOLVE_SAMPLE", 5):
            assert tidal_sample_catalog_queries(queries) == ["q0", "q1", "q2", "q3", "q4"]

    def test_short_list_returns_all(self):
        assert tidal_sample_catalog_queries(["a", "b"]) == ["a", "b"]


def _make_resp(status: int, body: str):
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)
    return resp


def _patch_session_scope(mock_session):
    @asynccontextmanager
    async def _fake_scope(*args, **kwargs):
        yield mock_session

    return patch("bot.services.tidal.session_scope", _fake_scope)


class TestTidalTrackPattern:
    def test_matches_track_url_with_slug(self):
        assert TIDAL_TRACK_PATTERN.search(TIDAL_TRACK_URL)
        assert TIDAL_TRACK_PATTERN.search(TIDAL_TRACK_URL).group(1) == "110653480"

    def test_matches_listen_subdomain(self):
        assert TIDAL_TRACK_PATTERN.search("https://listen.tidal.com/track/110653480")

    def test_album_url_not_matched_as_track(self):
        assert TIDAL_TRACK_PATTERN.search(TIDAL_ALBUM_URL) is None

    def test_no_match_non_tidal(self):
        assert TIDAL_TRACK_PATTERN.search("https://youtube.com/watch?v=abc") is None

    def test_no_match_invalid_path(self):
        assert TIDAL_TRACK_PATTERN.search("https://tidal.com/artist/123") is None


class TestTidalAlbumPattern:
    def test_matches_album_url(self):
        m = TIDAL_ALBUM_PATTERN.search(TIDAL_ALBUM_URL)
        assert m and m.group(1) == "476908869"


class TestTidalUrlToSearchQuery:
    @pytest.mark.asyncio
    async def test_success_returns_title(self):
        html = f'<meta property="og:title" content="{TIDAL_TRACK_TITLE}">'
        resp = _make_resp(200, html)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == TIDAL_TRACK_TITLE

    @pytest.mark.asyncio
    async def test_success_unescapes_html_entities(self):
        html = '<meta property="og:title" content="Excision &amp; Dion Timmer - Time Stood Still">'
        resp = _make_resp(200, html)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == TIDAL_TRACK_TITLE

    @pytest.mark.asyncio
    async def test_alt_og_title_order(self):
        html = '<meta content="Artist - Song" property="og:title">'
        resp = _make_resp(200, html)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == "Artist - Song"

    @pytest.mark.asyncio
    async def test_playlist_returns_none(self):
        result = await tidal_url_to_search_query(TIDAL_PLAYLIST_URL)
        assert result is None

    @pytest.mark.asyncio
    async def test_album_returns_none(self):
        result = await tidal_url_to_search_query(TIDAL_ALBUM_URL)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        result = await tidal_url_to_search_query("https://youtube.com/watch?v=abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        resp = _make_resp(404, "")
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            __aenter__=AsyncMock(side_effect=aiohttp.ClientError("connection failed")),
            __aexit__=AsyncMock(return_value=None),
        )
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_during_get_returns_none(self):
        bad_ctx = MagicMock()
        bad_ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("fetch failed"))
        bad_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.get.return_value = bad_ctx
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_first_pattern_too_long_falls_through_to_alt(self):
        long_title = "x" * 201
        html = f'<meta property="og:title" content="{long_title}">\n<meta content="Fallback Title" property="og:title">'
        resp = _make_resp(200, html)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == "Fallback Title"

    @pytest.mark.asyncio
    async def test_no_og_title_returns_none(self):
        resp = _make_resp(200, "<html><body>no meta</body></html>")
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result is None


class TestTidalPlaylistToSearchQueries:
    def _make_json_resp(self, items: list[dict]):
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"items": items})
        return resp

    @pytest.mark.asyncio
    async def test_success_returns_search_queries(self):
        items = [
            {"title": "Blood Wolf", "artist": {"name": "Dance Gavin Dance"}},
            {"title": "Reborn", "artist": {"name": "Delta Heavy"}},
        ]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result == [
                "Dance Gavin Dance - Blood Wolf",
                "Delta Heavy - Reborn",
            ]

    @pytest.mark.asyncio
    async def test_track_title_only_no_artist(self):
        items = [{"title": "Instrumental"}]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result == ["Instrumental"]

    @pytest.mark.asyncio
    async def test_track_no_title_skipped(self):
        items = [
            {"artist": {"name": "Someone"}},
            {"title": "Real Song", "artist": {"name": "Band"}},
        ]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result == ["Band - Real Song"]

    @pytest.mark.asyncio
    async def test_pagination_second_page(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 3):
            page1 = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3)]
            page2 = [{"title": "Last", "artist": {"name": "B"}}]
            resp1 = self._make_json_resp(page1)
            resp2 = self._make_json_resp(page2)
            ctx1 = MagicMock(
                __aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock(return_value=None)
            )
            ctx2 = MagicMock(
                __aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.side_effect = [ctx1, ctx2]
            with _patch_session_scope(mock_session):
                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
                assert result == ["A - Song0", "A - Song1", "A - Song2", "B - Last"]

    @pytest.mark.asyncio
    async def test_sample_caps_resolve_count(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_CATALOG_MAX", 5):
            items = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(8)]
            resp = self._make_json_resp(items)
            ctx = MagicMock(
                __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            with _patch_session_scope(mock_session):
                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
                assert result == ["A - Song0", "A - Song1", "A - Song2", "A - Song3", "A - Song4"]

    @pytest.mark.asyncio
    async def test_exits_while_by_max_tracks_condition(self):
        with (
            patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 3),
            patch("bot.services.tidal.TIDAL_PLAYLIST_CATALOG_MAX", 5),
        ):
            page1 = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3)]
            page2 = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3, 6)]
            resp1 = self._make_json_resp(page1)
            resp2 = self._make_json_resp(page2)
            resp3 = self._make_json_resp([])
            ctx1 = MagicMock(
                __aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock(return_value=None)
            )
            ctx2 = MagicMock(
                __aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock(return_value=None)
            )
            ctx3 = MagicMock(
                __aenter__=AsyncMock(return_value=resp3), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.side_effect = [ctx1, ctx2, ctx3]
            with _patch_session_scope(mock_session):
                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
                assert result == [
                    "A - Song0",
                    "A - Song1",
                    "A - Song2",
                    "A - Song3",
                    "A - Song4",
                ]

    @pytest.mark.asyncio
    async def test_empty_items_breaks(self):
        resp = self._make_json_resp([])
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        result = await tidal_playlist_to_search_queries("https://youtube.com/playlist/abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        resp = MagicMock(status=404)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            __aenter__=AsyncMock(side_effect=aiohttp.ClientError("connection failed")),
            __aexit__=AsyncMock(return_value=None),
        )
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_catalog_max_short_circuits_within_page(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_CATALOG_MAX", 2):
            items = [{"title": f"S{i}", "artist": {"name": "A"}} for i in range(5)]
            resp = self._make_json_resp(items)
            ctx = MagicMock(
                __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            with _patch_session_scope(mock_session):
                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result == ["A - S0", "A - S1"]
            mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_json_raises_client_error_returns_none(self):
        resp = MagicMock(status=200)
        resp.json = AsyncMock(side_effect=aiohttp.ClientError("parse"))
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            assert await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL) is None

    @pytest.mark.asyncio
    async def test_pagination_then_empty_page_finishes_while(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 1):
            resp1 = self._make_json_resp([{"title": "S0", "artist": {"name": "A"}}])
            resp2 = self._make_json_resp([{"title": "S1", "artist": {"name": "A"}}])
            resp3 = self._make_json_resp([])
            ctx1 = MagicMock(
                __aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock(return_value=None)
            )
            ctx2 = MagicMock(
                __aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock(return_value=None)
            )
            ctx3 = MagicMock(
                __aenter__=AsyncMock(return_value=resp3), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.side_effect = [ctx1, ctx2, ctx3]
            with _patch_session_scope(mock_session):
                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result == ["A - S0", "A - S1"]
            assert mock_session.get.call_count == 3

    @pytest.mark.asyncio
    async def test_full_page_then_while_condition_stops_second_fetch(self):
        with (
            patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 5),
            patch("bot.services.tidal.TIDAL_PLAYLIST_CATALOG_MAX", 3),
        ):
            items = [{"title": f"S{i}", "artist": {"name": "A"}} for i in range(5)]
            resp = self._make_json_resp(items)
            ctx = MagicMock(
                __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            with _patch_session_scope(mock_session):
                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result == ["A - S0", "A - S1", "A - S2"]
            mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_error_during_get_returns_none(self):
        bad_ctx = MagicMock()
        bad_ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("fetch failed"))
        bad_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.get.return_value = bad_ctx
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result is None


class TestTidalMixToSearchQueries:
    def _make_json_resp(self, items: list[dict]):
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"items": items})
        return resp

    @pytest.mark.asyncio
    async def test_success_returns_search_queries(self):
        items = [
            {"title": "Song A", "artist": {"name": "Artist A"}},
            {"title": "Song B", "artist": {"name": "Artist B"}},
        ]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_mix_to_search_queries(TIDAL_MIX_URL)
            assert result == ["Artist A - Song A", "Artist B - Song B"]

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        result = await tidal_mix_to_search_queries("https://youtube.com/mix/abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            __aenter__=AsyncMock(side_effect=aiohttp.ClientError("connection failed")),
            __aexit__=AsyncMock(return_value=None),
        )
        with _patch_session_scope(mock_session):
            result = await tidal_mix_to_search_queries(TIDAL_MIX_URL)
            assert result is None


class TestTidalAlbumToSearchQueries:
    def _make_json_resp(self, items: list[dict]):
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"items": items})
        return resp

    @pytest.mark.asyncio
    async def test_playlist_catalog_start_returns_first_page_and_continue(self):
        items = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3)]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_playlist_catalog_start(TIDAL_PLAYLIST_URL)
        assert result is not None
        queries, path, offset = result
        assert queries == ["A - Song0", "A - Song1", "A - Song2"]
        assert path is None
        assert offset == 0

    @pytest.mark.asyncio
    async def test_playlist_catalog_start_sets_continue_on_full_page(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 3):
            page1 = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3)]
            resp = self._make_json_resp(page1)
            ctx = MagicMock(
                __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            with _patch_session_scope(mock_session):
                result = await tidal_playlist_catalog_start(TIDAL_PLAYLIST_URL)
        assert result is not None
        queries, path, offset = result
        assert len(queries) == 3
        assert path is not None
        assert offset == 3

    @pytest.mark.asyncio
    async def test_mix_catalog_start(self):
        items = [{"title": "Mix Song", "artist": {"name": "DJ"}}]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_mix_catalog_start(TIDAL_MIX_URL)
        assert result == (["DJ - Mix Song"], None, 0)

    @pytest.mark.asyncio
    async def test_fetch_catalog_page_wrapper(self):
        items = [{"title": "Song", "artist": {"name": "A"}}]
        resp = MagicMock(status=200)
        resp.json = AsyncMock(return_value={"items": items})
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            from bot.services.tidal import tidal_fetch_catalog_page

            result = await tidal_fetch_catalog_page("playlists/u/tracks", 0)
        assert result == (["A - Song"], None)

    @pytest.mark.asyncio
    async def test_catalog_start_returns_none_when_page_fails(self):
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            __aenter__=AsyncMock(return_value=MagicMock(status=404)),
            __aexit__=AsyncMock(return_value=None),
        )
        with _patch_session_scope(mock_session):
            assert await tidal_playlist_catalog_start(TIDAL_PLAYLIST_URL) is None

    @pytest.mark.asyncio
    async def test_catalog_start_returns_none_when_first_page_empty(self):
        resp = self._make_json_resp([])
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            assert await tidal_playlist_catalog_start(TIDAL_PLAYLIST_URL) is None

    @pytest.mark.asyncio
    async def test_success_returns_queries(self):
        items = [
            {"title": "Song A", "artist": {"name": "Artist A"}},
            {"title": "Song B", "artist": {"name": "Artist B"}},
        ]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_album_to_search_queries(TIDAL_ALBUM_URL)
        assert result == ["Artist A - Song A", "Artist B - Song B"]

    @pytest.mark.asyncio
    async def test_preserves_album_track_order(self):
        items = [
            {"title": "First", "artist": {"name": "Band"}},
            {"title": "Second", "artist": {"name": "Band"}},
            {"title": "Third", "artist": {"name": "Band"}},
        ]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_album_to_search_queries(TIDAL_ALBUM_URL)
        assert result == ["Band - First", "Band - Second", "Band - Third"]

    @pytest.mark.asyncio
    async def test_album_pagination_fetches_second_page(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 3):
            page1 = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3)]
            page2 = [{"title": "Last", "artist": {"name": "B"}}]
            resp1 = self._make_json_resp(page1)
            resp2 = self._make_json_resp(page2)
            ctx1 = MagicMock(
                __aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock(return_value=None)
            )
            ctx2 = MagicMock(
                __aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.side_effect = [ctx1, ctx2]
            with _patch_session_scope(mock_session):
                result = await tidal_album_to_search_queries(TIDAL_ALBUM_URL)
            assert result == ["A - Song0", "A - Song1", "A - Song2", "B - Last"]
            assert mock_session.get.call_count == 2

    @pytest.mark.asyncio
    async def test_non_album_url_returns_none(self):
        assert await tidal_album_to_search_queries(TIDAL_TRACK_URL) is None

    @pytest.mark.asyncio
    async def test_empty_items_returns_none(self):
        resp = self._make_json_resp([])
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            assert await tidal_album_to_search_queries(TIDAL_ALBUM_URL) is None
