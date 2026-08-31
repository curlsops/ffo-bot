from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from bot.services.tidal import (
    TIDAL_ALBUM_PATTERN,
    TIDAL_TRACK_PATTERN,
    tidal_album_catalog_start,
    tidal_mix_catalog_start,
    tidal_playlist_catalog_start,
    tidal_url_to_search_query,
)

TIDAL_TRACK_URL = "https://tidal.com/track/110653480/u"
TIDAL_ALBUM_URL = "https://tidal.com/album/476908869/u"
TIDAL_TRACK_TITLE = "Excision & Dion Timmer - Time Stood Still"
TIDAL_PLAYLIST_URL = "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd"
TIDAL_MIX_URL = "https://tidal.com/browse/mix/3f4f1385-aa86-46e5-a6ad-cb18248be3cd"


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


class TestTidalCatalogStart:
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
    async def test_album_catalog_start_returns_first_page_and_continue(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 3):
            items = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3)]
            resp = self._make_json_resp(items)
            ctx = MagicMock(
                __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
            )
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            with _patch_session_scope(mock_session):
                result = await tidal_album_catalog_start(TIDAL_ALBUM_URL)
        assert result is not None
        queries, path, offset = result
        assert len(queries) == 3
        assert path is not None
        assert offset == 3

    @pytest.mark.asyncio
    async def test_album_catalog_start_no_continue_on_short_page(self):
        items = [{"title": "Song", "artist": {"name": "A"}}]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            result = await tidal_album_catalog_start(TIDAL_ALBUM_URL)
        assert result == (["A - Song"], None, 0)

    @pytest.mark.asyncio
    async def test_album_catalog_start_non_album_url_returns_none(self):
        assert await tidal_album_catalog_start(TIDAL_TRACK_URL) is None

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
    async def test_fetch_catalog_page_skips_items_without_title(self):
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
            from bot.services.tidal import tidal_fetch_catalog_page

            result = await tidal_fetch_catalog_page("playlists/u/tracks", 0)
        assert result == (["Band - Real Song"], None)

    @pytest.mark.asyncio
    async def test_fetch_catalog_page_title_only_no_artist(self):
        items = [{"title": "Instrumental"}]
        resp = self._make_json_resp(items)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = ctx
        with _patch_session_scope(mock_session):
            from bot.services.tidal import tidal_fetch_catalog_page

            result = await tidal_fetch_catalog_page("playlists/u/tracks", 0)
        assert result == (["Instrumental"], None)

    @pytest.mark.asyncio
    async def test_fetch_catalog_page_client_error_returns_none(self):
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            __aenter__=AsyncMock(side_effect=aiohttp.ClientError("connection failed")),
            __aexit__=AsyncMock(return_value=None),
        )
        with _patch_session_scope(mock_session):
            from bot.services.tidal import tidal_fetch_catalog_page

            result = await tidal_fetch_catalog_page("playlists/u/tracks", 0)
        assert result is None
