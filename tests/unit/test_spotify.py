from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from bot.services.spotify import (
    SPOTIFY_TRACK_PATTERN,
    spotify_url_to_search_query,
)

SPOTIFY_TRACK_URL = "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
SPOTIFY_TRACK_TITLE = "Michael Jackson - Billie Jean - Single Version"


def _make_json_resp(status: int, data: dict):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    return resp


class TestSpotifyTrackPattern:
    def test_matches_track_url(self):
        assert SPOTIFY_TRACK_PATTERN.search(SPOTIFY_TRACK_URL)
        assert SPOTIFY_TRACK_PATTERN.search(SPOTIFY_TRACK_URL).group(1) == "4iV5W9uYEdYUVa79Axb7Rh"

    def test_no_match_non_spotify(self):
        assert SPOTIFY_TRACK_PATTERN.search("https://youtube.com/watch?v=abc") is None

    def test_playlist_url_has_different_path(self):
        m = SPOTIFY_TRACK_PATTERN.search("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
        assert m is None


class TestSpotifyUrlToSearchQuery:
    @pytest.mark.asyncio
    async def test_success_returns_title(self):
        resp = _make_json_resp(200, {"title": SPOTIFY_TRACK_TITLE})
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.spotify.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
            assert result == SPOTIFY_TRACK_TITLE

    @pytest.mark.asyncio
    async def test_playlist_returns_none(self):
        result = await spotify_url_to_search_query(
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_album_returns_none(self):
        result = await spotify_url_to_search_query(
            "https://open.spotify.com/album/1bt6p2sru5F1kJG8j2Hk6o"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        result = await spotify_url_to_search_query("https://youtube.com/watch?v=abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        resp = _make_json_resp(404, {})
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.spotify.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        with patch("bot.services.spotify.aiohttp.ClientSession") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientError("connection failed")
            )
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_no_title_returns_none(self):
        resp = _make_json_resp(200, {"html": "<iframe>..."})
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.spotify.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_empty_title_returns_none(self):
        resp = _make_json_resp(200, {"title": ""})
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.spotify.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
            assert result is None

    @pytest.mark.asyncio
    async def test_title_not_string_returns_none(self):
        resp = _make_json_resp(200, {"title": 123})
        ctx = MagicMock(
            __aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None)
        )
        with patch("bot.services.spotify.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.return_value = ctx
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
            assert result is None
