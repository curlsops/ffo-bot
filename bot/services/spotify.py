import asyncio
import logging
import random
import re
from collections.abc import Callable
from typing import Any, TypeVar
from urllib.parse import quote

import aiohttp

from bot.utils.http_session import get_session, session_scope

logger = logging.getLogger(__name__)

SPOTAPI_PAGE_SIZE = 100
ARTIST_TRACK_POOL_TARGET = 100
ARTIST_PLAY_COUNT = 20
QUERY_MAX_LEN = 200

SPOTIFY_OEMBED = "https://open.spotify.com/oembed"
TIMEOUT = aiohttp.ClientTimeout(total=10)

SPOTIFY_TRACK_PATTERN = re.compile(
    r"https?://(?:open\.)?spotify\.com/track/([a-zA-Z0-9]+)",
    re.IGNORECASE,
)
SPOTIFY_PLAYLIST_PATTERN = re.compile(
    r"https?://(?:open\.)?spotify\.com/playlist/([a-zA-Z0-9]+)",
    re.IGNORECASE,
)
SPOTIFY_ALBUM_PATTERN = re.compile(
    r"https?://(?:open\.)?spotify\.com/album/([a-zA-Z0-9]+)",
    re.IGNORECASE,
)
SPOTIFY_ARTIST_PATTERN = re.compile(
    r"https?://(?:open\.)?spotify\.com/artist/([a-zA-Z0-9]+)",
    re.IGNORECASE,
)

T = TypeVar("T")


def _entry_to_search_query(title: str, artist: str | None) -> str:
    title = title.strip()
    if artist:
        artist = artist.strip()
        if artist:
            return f"{artist} - {title}"[:QUERY_MAX_LEN]
    return title[:QUERY_MAX_LEN]


def _artist_names_from_block(artists_field: Any) -> list[str]:
    if not isinstance(artists_field, dict):
        return []
    names: list[str] = []
    for item in artists_field.get("items") or []:
        if not isinstance(item, dict):
            continue
        profile = item.get("profile")
        if isinstance(profile, dict):
            name = profile.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


def _track_body_to_query(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    artists = _artist_names_from_block(body.get("artists"))
    if not artists:
        artists = _artist_names_from_block(body.get("firstArtist"))
    return _entry_to_search_query(name, artists[0] if artists else None)


def _playlist_item_to_query(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    item_v2 = item.get("itemV2")
    if not isinstance(item_v2, dict):
        return None
    return _track_body_to_query(item_v2.get("data"))


def _wrapped_track_item_to_query(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    track = item.get("track")
    if isinstance(track, dict):
        return _track_body_to_query(track)
    return _track_body_to_query(item)


def _search_track_item_to_query(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    wrapped = item.get("item")
    if isinstance(wrapped, dict):
        return _track_body_to_query(wrapped.get("data"))
    return None


async def _run_spotapi(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _sync_playlist_catalog(playlist_id: str) -> list[str] | None:
    from spotapi.playlist import PublicPlaylist

    playlist = PublicPlaylist(playlist_id)
    first = playlist.get_playlist_info(limit=SPOTAPI_PAGE_SIZE, offset=0)
    content = first["data"]["playlistV2"]["content"]
    total = int(content.get("totalCount") or 0)
    queries: list[str] = []

    def consume(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            q = _playlist_item_to_query(item)
            if q:
                queries.append(q)

    consume(content.get("items"))
    offset = SPOTAPI_PAGE_SIZE
    while offset < total:
        page = playlist.get_playlist_info(limit=SPOTAPI_PAGE_SIZE, offset=offset)
        consume(page["data"]["playlistV2"]["content"].get("items"))
        offset += SPOTAPI_PAGE_SIZE
    return queries or None


def _sync_album_catalog(album_id: str) -> list[str] | None:
    from spotapi.album import PublicAlbum

    album = PublicAlbum(album_id)
    first = album.get_album_info(limit=SPOTAPI_PAGE_SIZE, offset=0)
    tracks_v2 = first["data"]["albumUnion"]["tracksV2"]
    total = int(tracks_v2.get("totalCount") or 0)
    queries: list[str] = []

    def consume(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            q = _wrapped_track_item_to_query(item)
            if q:
                queries.append(q)

    consume(tracks_v2.get("items"))
    offset = SPOTAPI_PAGE_SIZE
    while offset < total:
        page = album.get_album_info(limit=SPOTAPI_PAGE_SIZE, offset=offset)
        consume(page["data"]["albumUnion"]["tracksV2"].get("items"))
        offset += SPOTAPI_PAGE_SIZE
    return queries or None


def _sync_artist_catalog(artist_id: str) -> list[str] | None:
    from spotapi.artist import Artist
    from spotapi.song import Song

    artist = Artist()
    overview = artist.get_artist(artist_id)
    artist_union = overview.get("data", {}).get("artistUnion") or {}
    profile_raw = artist_union.get("profile")
    profile = profile_raw if isinstance(profile_raw, dict) else {}
    name_raw = profile.get("name")
    artist_name = name_raw if isinstance(name_raw, str) else None

    pool: list[str] = []
    seen: set[str] = set()

    def add_query(q: str | None) -> None:
        if not q or q in seen:
            return
        seen.add(q)
        pool.append(q)

    top_items = ((artist_union.get("discography") or {}).get("topTracks") or {}).get("items") or []
    for item in top_items:
        add_query(_wrapped_track_item_to_query(item))
        if len(pool) >= ARTIST_TRACK_POOL_TARGET:
            break

    if len(pool) < ARTIST_TRACK_POOL_TARGET and artist_name:
        song = Song()
        offset = 0
        while len(pool) < ARTIST_TRACK_POOL_TARGET:
            search = song.query_songs(artist_name, limit=SPOTAPI_PAGE_SIZE, offset=offset)
            items = (
                search.get("data", {}).get("searchV2", {}).get("tracksV2", {}).get("items") or []
            )
            if not items:
                break
            for item in items:
                add_query(_search_track_item_to_query(item))
                if len(pool) >= ARTIST_TRACK_POOL_TARGET:
                    break
            if len(items) < SPOTAPI_PAGE_SIZE:
                break
            offset += SPOTAPI_PAGE_SIZE

    if not pool:
        return None
    count = min(ARTIST_PLAY_COUNT, len(pool))
    return random.sample(pool, count)


def _sync_track_query(track_id: str) -> str | None:
    from spotapi.song import Song

    info = Song().get_track_info(track_id)
    track_union = info.get("data", {}).get("trackUnion")
    return _track_body_to_query(track_union)


async def _spotify_catalog_from_url(
    pattern: re.Pattern[str],
    sync_fetch: Callable[[str], list[str] | None],
    url: str,
    *,
    error_label: str,
) -> list[str] | None:
    match = pattern.search(url)
    if not match:
        return None
    entity_id = match.group(1)
    from spotapi.exceptions import AlbumError, ArtistError, PlaylistError, SongError

    try:
        return await _run_spotapi(sync_fetch, entity_id)
    except (PlaylistError, AlbumError, ArtistError, SongError) as e:
        logger.debug("SpotAPI %s fetch failed for %s: %s", error_label, url, e)
        return None
    except Exception as e:
        logger.debug("SpotAPI %s fetch error for %s: %s", error_label, url, e)
        return None


async def spotify_playlist_catalog_queries(url: str) -> list[str] | None:
    return await _spotify_catalog_from_url(
        SPOTIFY_PLAYLIST_PATTERN, _sync_playlist_catalog, url, error_label="playlist"
    )


async def spotify_playlist_to_search_queries(url: str) -> list[str] | None:
    return await spotify_playlist_catalog_queries(url)


async def spotify_album_catalog_queries(url: str) -> list[str] | None:
    return await _spotify_catalog_from_url(
        SPOTIFY_ALBUM_PATTERN, _sync_album_catalog, url, error_label="album"
    )


async def spotify_album_to_search_queries(url: str) -> list[str] | None:
    return await spotify_album_catalog_queries(url)


async def spotify_artist_catalog_queries(url: str) -> list[str] | None:
    return await _spotify_catalog_from_url(
        SPOTIFY_ARTIST_PATTERN, _sync_artist_catalog, url, error_label="artist"
    )


async def spotify_url_to_search_query(url: str) -> str | None:
    if (
        SPOTIFY_PLAYLIST_PATTERN.search(url)
        or SPOTIFY_ALBUM_PATTERN.search(url)
        or SPOTIFY_ARTIST_PATTERN.search(url)
    ):
        return None
    track_match = SPOTIFY_TRACK_PATTERN.search(url)
    if not track_match:
        return None
    track_id = track_match.group(1)
    try:
        query = await _run_spotapi(_sync_track_query, track_id)
    except Exception as e:
        logger.debug("SpotAPI track fetch failed for %s: %s", url, e)
        query = None
    if query:
        return query
    oembed_url = f"{SPOTIFY_OEMBED}?url={quote(url, safe='')}"
    try:
        async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
            async with session.get(oembed_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except aiohttp.ClientError as e:
        logger.debug("Spotify oEmbed fetch failed for %s: %s", url, e)
        return None
    title = data.get("title")
    if not title or not isinstance(title, str):
        return None
    title = title.strip()[:QUERY_MAX_LEN]
    return title or None
