from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from bot.services.tidal import (
    TIDAL_MIX_PATTERN,
    TIDAL_PLAYLIST_PATTERN,
    TIDAL_TRACK_PATTERN,
    tidal_mix_to_search_queries,
    tidal_playlist_to_search_queries,
    tidal_url_to_search_query,
)

TIDAL_TRACK_URL = "https://tidal.com/track/110653480/u"
TIDAL_TRACK_TITLE = "Excision & Dion Timmer - Time Stood Still"
TIDAL_PLAYLIST_URL = "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd"
TIDAL_MIX_URL = "https://tidal.com/browse/mix/3f4f1385-aa86-46e5-a6ad-cb18248be3cd"


def _make_resp(status: int, body: str):
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)
    return resp


class TestTidalTrackPattern:
    def test_matches_track_url_with_slug(self):
        assert TIDAL_TRACK_PATTERN.search(TIDAL_TRACK_URL)
        assert TIDAL_TRACK_PATTERN.search(TIDAL_TRACK_URL).group(1) == "110653480"

    def test_matches_listen_subdomain(self):
        assert TIDAL_TRACK_PATTERN.search("https://listen.tidal.com/track/110653480")

    def test_no_match_non_tidal(self):
        assert TIDAL_TRACK_PATTERN.search("https://youtube.com/watch?v=abc") is None

    def test_no_match_invalid_path(self):
        assert TIDAL_TRACK_PATTERN.search("https://tidal.com/artist/123") is None


class TestTidalUrlToSearchQuery:
    @pytest.mark.asyncio
    async def test_success_returns_title(self):
        html = f'<meta property="og:title" content="{TIDAL_TRACK_TITLE}">'
        resp = _make_resp(200, html)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == TIDAL_TRACK_TITLE

    @pytest.mark.asyncio
    async def test_success_unescapes_html_entities(self):
        html = '<meta property="og:title" content="Excision &amp; Dion Timmer - Time Stood Still">'
        resp = _make_resp(200, html)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == TIDAL_TRACK_TITLE

    @pytest.mark.asyncio
    async def test_alt_og_title_order(self):
        html = '<meta content="Artist - Song" property="og:title">'
        resp = _make_resp(200, html)
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == "Artist - Song"

    @pytest.mark.asyncio
    async def test_playlist_returns_none(self):
        result = await tidal_url_to_search_query(TIDAL_PLAYLIST_URL)
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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientError("connection failed")
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_during_get_returns_none(self):
        bad_ctx = MagicMock()
        bad_ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("fetch failed"))
        bad_ctx.__aexit__ = AsyncMock(return_value=None)
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = bad_ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_url_to_search_query(TIDAL_TRACK_URL)
            assert result == "Fallback Title"

    @pytest.mark.asyncio
    async def test_no_og_title_returns_none(self):
        resp = _make_resp(200, "<html><body>no meta</body></html>")
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
            with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
                mock_session = MagicMock()
                mock_session.get.side_effect = [ctx1, ctx2]
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
                assert result == ["A - Song0", "A - Song1", "A - Song2", "B - Last"]

    @pytest.mark.asyncio
    async def test_hits_max_tracks_break(self):
        with patch("bot.services.tidal.TIDAL_PLAYLIST_MAX_TRACKS", 5):
            items = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(8)]
            resp = self._make_json_resp(items)
            ctx = MagicMock(
                __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
            )
            with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
                mock_session = MagicMock()
                mock_session.get.return_value = ctx
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
                assert result == ["A - Song0", "A - Song1", "A - Song2", "A - Song3", "A - Song4"]

    @pytest.mark.asyncio
    async def test_exits_while_by_max_tracks_condition(self):
        with (
            patch("bot.services.tidal.TIDAL_PLAYLIST_PAGE_SIZE", 3),
            patch("bot.services.tidal.TIDAL_PLAYLIST_MAX_TRACKS", 5),
        ):
            page1 = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3)]
            page2 = [{"title": f"Song{i}", "artist": {"name": "A"}} for i in range(3, 6)]
            resp1 = self._make_json_resp(page1)
            resp2 = self._make_json_resp(page2)
            ctx1 = MagicMock(
                __aenter__=AsyncMock(return_value=resp1), __aexit__=AsyncMock(return_value=None)
            )
            ctx2 = MagicMock(
                __aenter__=AsyncMock(return_value=resp2), __aexit__=AsyncMock(return_value=None)
            )
            with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
                mock_session = MagicMock()
                mock_session.get.side_effect = [ctx1, ctx2]
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientError("connection failed")
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_playlist_to_search_queries(TIDAL_PLAYLIST_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_during_get_returns_none(self):
        bad_ctx = MagicMock()
        bad_ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("fetch failed"))
        bad_ctx.__aexit__ = AsyncMock(return_value=None)
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = bad_ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

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
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_mix_to_search_queries(TIDAL_MIX_URL)
            assert result == ["Artist A - Song A", "Artist B - Song B"]

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        result = await tidal_mix_to_search_queries("https://youtube.com/mix/abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        with patch("bot.services.tidal.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientError("connection failed")
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await tidal_mix_to_search_queries(TIDAL_MIX_URL)
            assert result is None
