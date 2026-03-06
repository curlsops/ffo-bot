from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from bot.services import spotify as spotify_module
from bot.services.spotify import (
    SPOTIFY_PLAYLIST_PATTERN,
    SPOTIFY_TRACK_PATTERN,
    _get_spotify_token,
    spotify_playlist_to_search_queries,
    spotify_url_to_search_query,
)

SPOTIFY_TRACK_URL = "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
SPOTIFY_TRACK_TITLE = "Michael Jackson - Billie Jean - Single Version"
PLAYLIST_URL = "https://open.spotify.com/playlist/abc"
CREDS = ("cid", "secret")
TOKEN_OK = MagicMock(status=200, json=AsyncMock(return_value={"access_token": "tok"}))


def _make_json_resp(status: int, data: dict):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    return resp


def _track(name: str, artists: list[str], is_local: bool = False) -> dict:
    return {
        "track": {"name": name, "artists": [{"name": a} for a in artists], "is_local": is_local}
    }


def _items(count: int, artist: str = "A") -> list:
    return [_track(f"Track{i}", [artist]) for i in range(count)]


def _playlist_resp(items: list) -> MagicMock:
    return MagicMock(status=200, json=AsyncMock(return_value={"items": items}))


def _mock_session(post_resp=None, get_resp=None, post_raises=None, get_raises=None):
    if post_raises is not None:
        post_ctx = MagicMock(
            __aenter__=AsyncMock(side_effect=post_raises), __aexit__=AsyncMock(return_value=None)
        )
    else:
        post_ctx = MagicMock(
            __aenter__=AsyncMock(return_value=post_resp), __aexit__=AsyncMock(return_value=None)
        )
    session = MagicMock()
    session.post = MagicMock(return_value=post_ctx)
    if get_raises is not None:
        get_ctx = MagicMock(
            __aenter__=AsyncMock(side_effect=get_raises), __aexit__=AsyncMock(return_value=None)
        )
        session.get = MagicMock(return_value=get_ctx)
    elif get_resp is not None:
        get_ctx = MagicMock(
            __aenter__=AsyncMock(return_value=get_resp), __aexit__=AsyncMock(return_value=None)
        )
        session.get = MagicMock(return_value=get_ctx)
    return session


@contextmanager
def _patch_client_session(session=None, raise_on_enter=None):
    with patch("bot.services.spotify.aiohttp.ClientSession") as mock_cls:
        if raise_on_enter is not None:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=raise_on_enter)
        else:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        yield mock_cls


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
        session = _mock_session(None, resp)
        with _patch_client_session(session):
            result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
            assert result == SPOTIFY_TRACK_TITLE

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
            "https://open.spotify.com/album/1bt6p2sru5F1kJG8j2Hk6o",
            "https://youtube.com/watch?v=abc",
        ],
    )
    async def test_non_track_url_returns_none(self, url):
        assert await spotify_url_to_search_query(url) is None

    @pytest.mark.asyncio
    async def test_client_error_returns_none(self):
        with _patch_client_session(raise_on_enter=aiohttp.ClientError("connection failed")):
            assert await spotify_url_to_search_query(SPOTIFY_TRACK_URL) is None

    @pytest.mark.asyncio
    async def test_oembed_non_200_returns_none(self):
        resp = MagicMock(status=404)
        resp.json = AsyncMock()
        session = _mock_session(None, resp)
        with _patch_client_session(session):
            assert await spotify_url_to_search_query(SPOTIFY_TRACK_URL) is None

    @pytest.mark.asyncio
    async def test_oembed_empty_title_returns_none(self):
        resp = _make_json_resp(200, {"title": ""})
        session = _mock_session(None, resp)
        with _patch_client_session(session):
            assert await spotify_url_to_search_query(SPOTIFY_TRACK_URL) is None

    @pytest.mark.asyncio
    async def test_oembed_get_raises_client_error_returns_none(self):
        session = MagicMock()
        session.get = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(side_effect=aiohttp.ClientError("timeout")),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        with _patch_client_session(session):
            assert await spotify_url_to_search_query(SPOTIFY_TRACK_URL) is None


class TestSpotifyPlaylistPattern:
    def test_matches_playlist_url(self):
        url = "https://open.spotify.com/playlist/5bCeKZhm0Vrk4cOydmil2N?si=04bf39def50c41bc"
        m = SPOTIFY_PLAYLIST_PATTERN.search(url)
        assert m is not None
        assert m.group(1) == "5bCeKZhm0Vrk4cOydmil2N"


class TestSpotifyPlaylistToSearchQueries:
    @pytest.fixture(autouse=True)
    def clear_token_cache(self):
        spotify_module._SPOTIFY_TOKEN_CACHE = None
        yield

    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        result = await spotify_playlist_to_search_queries(
            "https://open.spotify.com/playlist/abc123", None, None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_non_playlist_url_returns_none(self):
        result = await spotify_playlist_to_search_queries(
            "https://open.spotify.com/track/abc", "cid", "secret"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_success_returns_search_queries(self):
        items = [
            _track("Slave Knight Gael", ["Yuka Kitamura"]),
            _track("Soul of Cinder", ["Yuka Kitamura"]),
        ]
        session = _mock_session(TOKEN_OK, _playlist_resp(items))
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(
                "https://open.spotify.com/playlist/5bCeKZhm0Vrk4cOydmil2N", *CREDS
            )
        assert result == ["Yuka Kitamura - Slave Knight Gael", "Yuka Kitamura - Soul of Cinder"]

    @pytest.mark.asyncio
    async def test_local_track_skipped(self):
        items = [_track("Local", [], is_local=True), _track("Remote", ["Artist"])]
        session = _mock_session(TOKEN_OK, _playlist_resp(items))
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result == ["Artist - Remote"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,token_json",
        [
            (401, {}),
            (500, {}),
            (200, {"token": "bad_key"}),
            (200, {"access_token": 123}),
        ],
    )
    async def test_token_post_failure_returns_none(self, status, token_json):
        token_resp = MagicMock(status=status, json=AsyncMock(return_value=token_json))
        session = _mock_session(token_resp)
        with _patch_client_session(session):
            assert await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS) is None

    @pytest.mark.asyncio
    async def test_token_post_client_error_returns_none(self):
        session = _mock_session(post_raises=aiohttp.ClientError("network"))
        with _patch_client_session(session):
            assert await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS) is None

    @pytest.mark.asyncio
    async def test_get_spotify_token_success_returns_token(self):
        session = _mock_session(TOKEN_OK)
        with _patch_client_session(session):
            result = await _get_spotify_token(*CREDS)
        assert result == "tok"

    @pytest.mark.asyncio
    async def test_get_spotify_token_non_200_returns_none(self):
        token_resp = MagicMock(status=401, json=AsyncMock(return_value={}))
        session = _mock_session(token_resp)
        with _patch_client_session(session):
            result = await _get_spotify_token(*CREDS)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_spotify_token_client_error_returns_none(self):
        session = _mock_session(post_raises=aiohttp.ClientError("network"))
        with _patch_client_session(session):
            result = await _get_spotify_token(*CREDS)
        assert result is None

    @pytest.mark.asyncio
    async def test_token_post_non_200_returns_none(self):
        token_resp = MagicMock(status=401, json=AsyncMock(return_value={}))
        session = _mock_session(token_resp)
        with _patch_client_session(session):
            assert await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS) is None

    @pytest.mark.asyncio
    async def test_track_name_only_no_artists(self):
        session = _mock_session(TOKEN_OK, _playlist_resp([_track("Instrumental", [])]))
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result == ["Instrumental"]

    @pytest.mark.asyncio
    async def test_track_no_name_skipped(self):
        items = [{"track": {"artists": [{"name": "A"}], "is_local": False}}, _track("Valid", ["B"])]
        session = _mock_session(TOKEN_OK, _playlist_resp(items))
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result == ["B - Valid"]

    @pytest.mark.asyncio
    async def test_playlist_api_401_clears_cache_and_returns_none(self):
        spotify_module._SPOTIFY_TOKEN_CACHE = ("old", 0.0)
        playlist_resp = MagicMock(status=401, json=AsyncMock(return_value={}))
        session = _mock_session(TOKEN_OK, playlist_resp)
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result is None
        assert spotify_module._SPOTIFY_TOKEN_CACHE is None

    @pytest.mark.asyncio
    async def test_playlist_api_non_200_returns_none(self):
        playlist_resp = MagicMock(status=403, json=AsyncMock(return_value={}))
        session = _mock_session(TOKEN_OK, playlist_resp)
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result is None

    @pytest.mark.asyncio
    async def test_playlist_api_client_error_returns_none(self):
        session = _mock_session(TOKEN_OK, get_raises=aiohttp.ClientError("timeout"))
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result is None

    @pytest.mark.asyncio
    async def test_playlist_full_page_stops_at_max_tracks(self):
        page1 = MagicMock(status=200, json=AsyncMock(return_value={"items": _items(50)}))
        session = _mock_session(TOKEN_OK, page1)
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert len(result) == 50
        assert result[0] == "A - Track0"
        assert result[49] == "A - Track49"

    @pytest.mark.asyncio
    async def test_playlist_pagination_fetches_second_page(self):
        invalid = [_track("", [])] * 25
        page1 = MagicMock(status=200, json=AsyncMock(return_value={"items": _items(25) + invalid}))
        page2 = MagicMock(
            status=200, json=AsyncMock(return_value={"items": [_track("Track25", ["A"])]})
        )
        get_ctxs = [
            MagicMock(
                __aenter__=AsyncMock(return_value=page1), __aexit__=AsyncMock(return_value=None)
            ),
            MagicMock(
                __aenter__=AsyncMock(return_value=page2), __aexit__=AsyncMock(return_value=None)
            ),
        ]
        session = _mock_session(TOKEN_OK)
        session.get = MagicMock(side_effect=get_ctxs)
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert len(result) == 26
        assert result[25] == "A - Track25"
        assert session.get.call_count == 2

    @pytest.mark.asyncio
    async def test_playlist_partial_page_stops_early(self):
        page1 = MagicMock(status=200, json=AsyncMock(return_value={"items": _items(30)}))
        session = _mock_session(TOKEN_OK, page1)
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert len(result) == 30
        assert result[29] == "A - Track29"

    @pytest.mark.asyncio
    async def test_token_cache_reused_on_second_call(self):
        spotify_module._SPOTIFY_TOKEN_CACHE = None
        session = _mock_session(TOKEN_OK, _playlist_resp([_track("A", ["X"])]))
        with _patch_client_session(session):
            r1 = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
            r2 = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert r1 == ["X - A"]
        assert r2 == ["X - A"]
        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_playlist_empty_items_returns_queries(self):
        playlist_resp = MagicMock(
            status=200, json=AsyncMock(return_value={"items": [_track("One", ["X"])]})
        )
        empty_resp = MagicMock(status=200, json=AsyncMock(return_value={"items": []}))
        get_ctxs = [
            MagicMock(
                __aenter__=AsyncMock(return_value=playlist_resp),
                __aexit__=AsyncMock(return_value=None),
            ),
            MagicMock(
                __aenter__=AsyncMock(return_value=empty_resp),
                __aexit__=AsyncMock(return_value=None),
            ),
        ]
        session = _mock_session(TOKEN_OK)
        session.get = MagicMock(side_effect=get_ctxs)
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result == ["X - One"]

    @pytest.mark.asyncio
    async def test_playlist_response_missing_items_key(self):
        playlist_resp = MagicMock(status=200, json=AsyncMock(return_value={}))
        session = _mock_session(TOKEN_OK, playlist_resp)
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result is None

    @pytest.mark.asyncio
    async def test_playlist_all_invalid_items_returns_none(self):
        items = [_track("", []), {"track": {"is_local": True}}]
        session = _mock_session(TOKEN_OK, _playlist_resp(items))
        with _patch_client_session(session):
            result = await spotify_playlist_to_search_queries(PLAYLIST_URL, *CREDS)
        assert result is None
