import random
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from spotapi.exceptions import AlbumError, ArtistError, PlaylistError, SongError

from bot.services import spotify as spotify_module
from bot.services.spotify import (
    ARTIST_PLAY_COUNT,
    ARTIST_TRACK_POOL_TARGET,
    SPOTAPI_PAGE_SIZE,
    SPOTIFY_ALBUM_PATTERN,
    SPOTIFY_ARTIST_PATTERN,
    SPOTIFY_PLAYLIST_PATTERN,
    SPOTIFY_TRACK_PATTERN,
    _artist_names_from_block,
    _entry_to_search_query,
    _playlist_item_to_query,
    _search_track_item_to_query,
    _sync_album_catalog,
    _sync_artist_catalog,
    _sync_playlist_catalog,
    _sync_track_query,
    _track_body_to_query,
    _wrapped_track_item_to_query,
    spotify_album_catalog_queries,
    spotify_album_to_search_queries,
    spotify_artist_catalog_queries,
    spotify_playlist_catalog_queries,
    spotify_playlist_to_search_queries,
    spotify_url_to_search_query,
)

SPOTIFY_TRACK_URL = "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
SPOTIFY_ALBUM_URL = "https://open.spotify.com/album/1abcdefghijklmnop"
SPOTIFY_PLAYLIST_URL = "https://open.spotify.com/playlist/abc"
SPOTIFY_ARTIST_URL = "https://open.spotify.com/artist/06HL4z0CvFAxyc27GXpf02"
SPOTIFY_TRACK_TITLE = "Michael Jackson - Billie Jean"


async def _run_sync(func, /, *args, **kwargs):
    return func(*args, **kwargs)


def _playlist_page(items: list, total: int, offset: int = 0) -> dict:
    return {
        "data": {
            "playlistV2": {
                "content": {
                    "totalCount": total,
                    "items": items,
                    "pagingInfo": {"offset": offset},
                }
            }
        }
    }


def _album_page(items: list, total: int) -> dict:
    return {"data": {"albumUnion": {"tracksV2": {"totalCount": total, "items": items}}}}


def _playlist_item(title: str, artist: str) -> dict:
    return {
        "itemV2": {
            "data": {
                "name": title,
                "artists": {"items": [{"profile": {"name": artist}}]},
            }
        }
    }


def _album_item(title: str, artist: str) -> dict:
    return {"track": {"name": title, "artists": {"items": [{"profile": {"name": artist}}]}}}


def _top_track_item(title: str, artist: str) -> dict:
    return _album_item(title, artist)


def _search_item(title: str, artist: str) -> dict:
    return {
        "item": {"data": {"name": title, "artists": {"items": [{"profile": {"name": artist}}]}}}
    }


@contextmanager
def _patch_run_spotapi():
    with patch.object(spotify_module, "_run_spotapi", side_effect=_run_sync):
        yield


@contextmanager
def _patch_client_session(session=None, raise_on_enter=None):
    if raise_on_enter is not None:
        session = MagicMock()
        session.get = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(side_effect=raise_on_enter),
                __aexit__=AsyncMock(return_value=None),
            )
        )
    with patch("bot.services.spotify.get_session", return_value=session):
        yield


class TestSpotifyPatterns:
    def test_track_pattern(self):
        assert SPOTIFY_TRACK_PATTERN.search(SPOTIFY_TRACK_URL).group(1) == "4iV5W9uYEdYUVa79Axb7Rh"

    def test_playlist_pattern(self):
        m = SPOTIFY_PLAYLIST_PATTERN.search(
            "https://open.spotify.com/playlist/5bCeKZhm0Vrk4cOydmil2N?si=x"
        )
        assert m.group(1) == "5bCeKZhm0Vrk4cOydmil2N"

    def test_album_pattern(self):
        assert SPOTIFY_ALBUM_PATTERN.search(SPOTIFY_ALBUM_URL).group(1) == "1abcdefghijklmnop"

    def test_artist_pattern(self):
        assert (
            SPOTIFY_ARTIST_PATTERN.search(SPOTIFY_ARTIST_URL).group(1) == "06HL4z0CvFAxyc27GXpf02"
        )


class TestSpotifyQueryHelpers:
    def test_entry_to_search_query_with_artist(self):
        assert _entry_to_search_query("Song", "Artist") == "Artist - Song"

    def test_entry_to_search_query_blank_artist_uses_title(self):
        assert _entry_to_search_query("Song", "   ") == "Song"

    def test_entry_to_search_query_title_only(self):
        assert _entry_to_search_query("Instrumental", None) == "Instrumental"

    def test_artist_names_from_block(self):
        block = {"items": [{"profile": {"name": "A"}}, {"profile": {"name": "B"}}]}
        assert _artist_names_from_block(block) == ["A", "B"]

    def test_artist_names_from_block_skips_invalid(self):
        assert _artist_names_from_block(None) == []
        block = {
            "items": [
                "bad",
                {"profile": "bad"},
                {"profile": {"name": ""}},
                {"profile": {"name": "Ok"}},
            ]
        }
        assert _artist_names_from_block(block) == ["Ok"]

    def test_track_body_to_query(self):
        body = {"name": "T", "artists": {"items": [{"profile": {"name": "Z"}}]}}
        assert _track_body_to_query(body) == "Z - T"

    def test_track_body_uses_first_artist_fallback(self):
        body = {
            "name": "T",
            "firstArtist": {"items": [{"profile": {"name": "FA"}}]},
        }
        assert _track_body_to_query(body) == "FA - T"

    def test_track_body_missing_name(self):
        assert _track_body_to_query({"artists": {}}) is None
        assert _track_body_to_query("not-a-dict") is None

    def test_playlist_item_to_query(self):
        assert _playlist_item_to_query(_playlist_item("A", "Z")) == "Z - A"

    def test_playlist_item_invalid(self):
        assert _playlist_item_to_query(None) is None
        assert _playlist_item_to_query({"itemV2": "x"}) is None

    def test_wrapped_track_item_to_query(self):
        assert _wrapped_track_item_to_query(_album_item("A", "Z")) == "Z - A"

    def test_wrapped_track_direct_body(self):
        assert _wrapped_track_item_to_query({"name": "Solo", "artists": {}}) == "Solo"

    def test_wrapped_track_invalid(self):
        assert _wrapped_track_item_to_query(None) is None

    def test_search_track_item_to_query(self):
        assert _search_track_item_to_query(_search_item("A", "Z")) == "Z - A"

    def test_search_track_item_invalid(self):
        assert _search_track_item_to_query(None) is None
        assert _search_track_item_to_query({"item": "x"}) is None


class TestRunSpotapi:
    @pytest.mark.asyncio
    async def test_run_spotapi_executes_in_executor(self):
        result = await spotify_module._run_spotapi(lambda x: x + 1, 1)
        assert result == 2


class TestSyncPlaylistCatalog:
    def test_consume_skips_non_list_items(self):
        pp = MagicMock()
        pp.get_playlist_info.return_value = _playlist_page(None, 0)
        with patch.object(spotify_module, "PublicPlaylist", return_value=pp):
            assert _sync_playlist_catalog("abc") is None

    def test_skips_unparseable_playlist_items(self):
        pp = MagicMock()
        items = [_playlist_item("Ok", "A"), {"itemV2": {"data": {"name": ""}}}]
        pp.get_playlist_info.return_value = _playlist_page(items, len(items))
        with patch.object(spotify_module, "PublicPlaylist", return_value=pp):
            result = _sync_playlist_catalog("abc")
        assert result == ["A - Ok"]

    def test_paginates_two_pages(self):
        pp = MagicMock()
        pp.get_playlist_info.side_effect = [
            _playlist_page([_playlist_item(f"T{i}", "A") for i in range(SPOTAPI_PAGE_SIZE)], 150),
            _playlist_page([_playlist_item("T100", "A")], 150, offset=SPOTAPI_PAGE_SIZE),
        ]
        with patch.object(spotify_module, "PublicPlaylist", return_value=pp):
            result = _sync_playlist_catalog("abc")
        assert len(result) == SPOTAPI_PAGE_SIZE + 1
        assert pp.get_playlist_info.call_count == 2

    def test_empty_returns_none(self):
        pp = MagicMock()
        pp.get_playlist_info.return_value = _playlist_page([], 0)
        with patch.object(spotify_module, "PublicPlaylist", return_value=pp):
            assert _sync_playlist_catalog("abc") is None


class TestSyncAlbumCatalog:
    def test_consume_skips_non_list_items(self):
        al = MagicMock()
        al.get_album_info.return_value = {
            "data": {"albumUnion": {"tracksV2": {"totalCount": 0, "items": None}}}
        }
        with patch.object(spotify_module, "PublicAlbum", return_value=al):
            assert _sync_album_catalog("album1") is None

    def test_skips_unparseable_album_items(self):
        al = MagicMock()
        items = [_album_item("Ok", "B"), {"track": {"name": ""}}]
        al.get_album_info.return_value = _album_page(items, len(items))
        with patch.object(spotify_module, "PublicAlbum", return_value=al):
            result = _sync_album_catalog("album1")
        assert result == ["B - Ok"]

    def test_paginates_album(self):
        al = MagicMock()
        al.get_album_info.side_effect = [
            _album_page([_album_item(f"T{i}", "B") for i in range(SPOTAPI_PAGE_SIZE)], 120),
            _album_page([_album_item("T100", "B")], 120),
        ]
        with patch.object(spotify_module, "PublicAlbum", return_value=al):
            result = _sync_album_catalog("album1")
        assert len(result) == SPOTAPI_PAGE_SIZE + 1


class TestSyncArtistCatalog:
    def test_top_tracks_break_when_pool_full(self):
        artist = MagicMock()
        artist.get_artist.return_value = {
            "data": {
                "artistUnion": {
                    "profile": {"name": "A"},
                    "discography": {
                        "topTracks": {
                            "items": [
                                _top_track_item(f"T{i}", "A")
                                for i in range(ARTIST_TRACK_POOL_TARGET + 5)
                            ]
                        }
                    },
                }
            }
        }
        with (
            patch.object(spotify_module, "Artist", return_value=artist),
            patch.object(spotify_module.random, "sample", side_effect=lambda pool, k: pool[:k]),
        ):
            result = _sync_artist_catalog("artist1")
        assert len(result) == ARTIST_PLAY_COUNT

    def test_search_stops_on_empty_page(self):
        artist = MagicMock()
        artist.get_artist.return_value = {
            "data": {
                "artistUnion": {
                    "profile": {"name": "Band"},
                    "discography": {"topTracks": {"items": [_top_track_item("One", "Band")]}},
                }
            }
        }
        song = MagicMock()
        song.query_songs.return_value = {"data": {"searchV2": {"tracksV2": {"items": []}}}}
        with (
            patch.object(spotify_module, "Artist", return_value=artist),
            patch.object(spotify_module, "Song", return_value=song),
            patch.object(spotify_module.random, "sample", side_effect=lambda pool, k: pool[:k]),
        ):
            result = _sync_artist_catalog("artist1")
        assert result == ["Band - One"]

    def test_top_tracks_then_search_supplement(self):
        artist = MagicMock()
        artist.get_artist.return_value = {
            "data": {
                "artistUnion": {
                    "profile": {"name": "Taylor Swift"},
                    "discography": {
                        "topTracks": {
                            "items": [_top_track_item(f"Top{i}", "Taylor Swift") for i in range(10)]
                        }
                    },
                }
            }
        }
        song = MagicMock()
        song.query_songs.return_value = {
            "data": {
                "searchV2": {
                    "tracksV2": {
                        "items": [
                            _search_item(f"Extra{i}", "Taylor Swift")
                            for i in range(ARTIST_TRACK_POOL_TARGET)
                        ]
                    }
                }
            }
        }
        with (
            patch.object(spotify_module, "Artist", return_value=artist),
            patch.object(spotify_module, "Song", return_value=song),
            patch.object(spotify_module.random, "sample", side_effect=lambda pool, k: pool[:k]),
        ):
            result = _sync_artist_catalog("artist1")
        assert len(result) == ARTIST_PLAY_COUNT
        assert result[0] == "Taylor Swift - Top0"

    def test_duplicate_queries_deduped(self):
        artist = MagicMock()
        artist.get_artist.return_value = {
            "data": {
                "artistUnion": {
                    "profile": {"name": "Band"},
                    "discography": {"topTracks": {"items": []}},
                }
            }
        }
        song = MagicMock()
        song.query_songs.return_value = {
            "data": {
                "searchV2": {
                    "tracksV2": {
                        "items": [
                            _search_item("Dup", "Band"),
                            _search_item("Dup", "Band"),
                            _search_item("Other", "Band"),
                        ]
                        + [_search_item(f"T{i}", "Band") for i in range(ARTIST_TRACK_POOL_TARGET)]
                    }
                }
            }
        }
        pool_before_sample: list[str] = []

        def sample_side_effect(pool: list[str], k: int) -> list[str]:
            pool_before_sample.extend(pool)
            return pool[:k]

        with (
            patch.object(spotify_module, "Artist", return_value=artist),
            patch.object(spotify_module, "Song", return_value=song),
            patch.object(spotify_module.random, "sample", side_effect=sample_side_effect),
        ):
            result = _sync_artist_catalog("artist1")
        assert pool_before_sample.count("Band - Dup") == 1
        assert "Band - Other" in result

    def test_search_pagination_until_pool_full(self):
        artist = MagicMock()
        artist.get_artist.return_value = {
            "data": {
                "artistUnion": {
                    "profile": {"name": "Band"},
                    "discography": {"topTracks": {"items": []}},
                }
            }
        }
        song = MagicMock()
        first_page = [
            *[_search_item(f"S{i}", "Band") for i in range(50)],
            *[{"item": "bad"} for _ in range(50)],
        ]
        song.query_songs.side_effect = [
            {"data": {"searchV2": {"tracksV2": {"items": first_page}}}},
            {
                "data": {
                    "searchV2": {
                        "tracksV2": {"items": [_search_item(f"X{i}", "Band") for i in range(50)]}
                    }
                }
            },
        ]
        with (
            patch.object(spotify_module, "Artist", return_value=artist),
            patch.object(spotify_module, "Song", return_value=song),
            patch.object(spotify_module.random, "sample", side_effect=lambda pool, k: pool[:k]),
        ):
            result = _sync_artist_catalog("artist1")
        assert len(result) == ARTIST_PLAY_COUNT
        assert song.query_songs.call_count == 2

    def test_empty_pool_returns_none(self):
        artist = MagicMock()
        artist.get_artist.return_value = {
            "data": {"artistUnion": {"profile": {}, "discography": {"topTracks": {"items": []}}}}
        }
        song = MagicMock()
        song.query_songs.return_value = {"data": {"searchV2": {"tracksV2": {"items": []}}}}
        with (
            patch.object(spotify_module, "Artist", return_value=artist),
            patch.object(spotify_module, "Song", return_value=song),
            patch.object(spotify_module.random, "sample", side_effect=lambda pool, k: pool[:k]),
        ):
            assert _sync_artist_catalog("artist1") is None


class TestSyncTrackQuery:
    def test_track_union_query(self):
        song = MagicMock()
        song.get_track_info.return_value = {
            "data": {
                "trackUnion": {
                    "name": "Billie Jean",
                    "artists": {"items": [{"profile": {"name": "Michael Jackson"}}]},
                }
            }
        }
        with patch.object(spotify_module, "Song", return_value=song):
            assert _sync_track_query("tid") == "Michael Jackson - Billie Jean"


class TestSpotifyUrlToSearchQuery:
    @pytest.mark.asyncio
    async def test_track_via_spotapi(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_track_query", return_value="Michael Jackson - Billie Jean"
            ):
                result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
        assert result == "Michael Jackson - Billie Jean"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
            "https://open.spotify.com/album/1bt6p2sru5F1kJG8j2Hk6o",
            "https://open.spotify.com/artist/06HL4z0CvFAxyc27GXpf02",
            "https://youtube.com/watch?v=abc",
        ],
    )
    async def test_non_single_track_url_returns_none(self, url):
        assert await spotify_url_to_search_query(url) is None

    @pytest.mark.asyncio
    async def test_track_generic_exception_falls_back_to_oembed(self):
        resp = MagicMock(status=200, json=AsyncMock(return_value={"title": "Fallback Title"}))
        session = MagicMock()
        session.get = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=resp),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_track_query", side_effect=RuntimeError("boom")
            ):
                with _patch_client_session(session):
                    result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
        assert result == "Fallback Title"

    @pytest.mark.asyncio
    async def test_oembed_non_200_returns_none(self):
        resp = MagicMock(status=404)
        session = MagicMock()
        session.get = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=resp),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        with _patch_run_spotapi():
            with patch.object(spotify_module, "_sync_track_query", return_value=None):
                with _patch_client_session(session):
                    assert await spotify_url_to_search_query(SPOTIFY_TRACK_URL) is None

    @pytest.mark.asyncio
    async def test_oembed_empty_title_returns_none(self):
        resp = MagicMock(status=200, json=AsyncMock(return_value={"title": ""}))
        session = MagicMock()
        session.get = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=resp),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        with _patch_run_spotapi():
            with patch.object(spotify_module, "_sync_track_query", return_value=None):
                with _patch_client_session(session):
                    assert await spotify_url_to_search_query(SPOTIFY_TRACK_URL) is None

    @pytest.mark.asyncio
    async def test_oembed_fallback_when_spotapi_fails(self):
        resp = MagicMock(status=200, json=AsyncMock(return_value={"title": SPOTIFY_TRACK_TITLE}))
        session = MagicMock()
        session.get = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=resp),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        with _patch_run_spotapi():
            with patch.object(spotify_module, "_sync_track_query", side_effect=SongError("x")):
                with _patch_client_session(session):
                    result = await spotify_url_to_search_query(SPOTIFY_TRACK_URL)
        assert result == SPOTIFY_TRACK_TITLE

    @pytest.mark.asyncio
    async def test_oembed_client_error_returns_none(self):
        with _patch_run_spotapi():
            with patch.object(spotify_module, "_sync_track_query", return_value=None):
                with _patch_client_session(raise_on_enter=aiohttp.ClientError("timeout")):
                    assert await spotify_url_to_search_query(SPOTIFY_TRACK_URL) is None


class TestSpotifyCatalogQueries:
    @pytest.mark.asyncio
    async def test_playlist_catalog_queries(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_playlist_catalog", return_value=["Z - A", "Z - B"]
            ):
                result = await spotify_playlist_catalog_queries(SPOTIFY_PLAYLIST_URL)
        assert result == ["Z - A", "Z - B"]

    @pytest.mark.asyncio
    async def test_playlist_catalog_playlist_error(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_playlist_catalog", side_effect=PlaylistError("private")
            ):
                assert await spotify_playlist_catalog_queries(SPOTIFY_PLAYLIST_URL) is None

    @pytest.mark.asyncio
    async def test_playlist_catalog_generic_error(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_playlist_catalog", side_effect=RuntimeError("boom")
            ):
                assert await spotify_playlist_catalog_queries(SPOTIFY_PLAYLIST_URL) is None

    @pytest.mark.asyncio
    async def test_playlist_non_url_returns_none(self):
        assert await spotify_playlist_catalog_queries("https://youtube.com/x") is None

    @pytest.mark.asyncio
    async def test_album_catalog_queries(self):
        with _patch_run_spotapi():
            with patch.object(spotify_module, "_sync_album_catalog", return_value=["Band - One"]):
                result = await spotify_album_catalog_queries(SPOTIFY_ALBUM_URL)
        assert result == ["Band - One"]

    @pytest.mark.asyncio
    async def test_album_non_url_returns_none(self):
        assert await spotify_album_catalog_queries("https://youtube.com/x") is None

    @pytest.mark.asyncio
    async def test_album_catalog_album_error(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_album_catalog", side_effect=AlbumError("missing")
            ):
                assert await spotify_album_catalog_queries(SPOTIFY_ALBUM_URL) is None

    @pytest.mark.asyncio
    async def test_artist_catalog_queries(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_artist_catalog", return_value=["A - 1", "A - 2"]
            ):
                result = await spotify_artist_catalog_queries(SPOTIFY_ARTIST_URL)
        assert result == ["A - 1", "A - 2"]

    @pytest.mark.asyncio
    async def test_artist_non_url_returns_none(self):
        assert await spotify_artist_catalog_queries("https://youtube.com/x") is None

    @pytest.mark.asyncio
    async def test_artist_catalog_artist_error(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_artist_catalog", side_effect=ArtistError("gone")
            ):
                assert await spotify_artist_catalog_queries(SPOTIFY_ARTIST_URL) is None

    @pytest.mark.asyncio
    async def test_aliases_delegate(self):
        with _patch_run_spotapi():
            with patch.object(
                spotify_module, "_sync_playlist_catalog", return_value=["x"]
            ) as pl_mock:
                assert await spotify_playlist_to_search_queries(SPOTIFY_PLAYLIST_URL) == ["x"]
                pl_mock.assert_called_once()
            with patch.object(spotify_module, "_sync_album_catalog", return_value=["y"]) as al_mock:
                assert await spotify_album_to_search_queries(SPOTIFY_ALBUM_URL) == ["y"]
                al_mock.assert_called_once()
