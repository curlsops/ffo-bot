import random
from typing import Any

SPOTAPI_PAGE_SIZE = 100
ARTIST_TRACK_POOL_TARGET = 100
ARTIST_PLAY_COUNT = 20
QUERY_MAX_LEN = 200

SPOTAPI_OPERATIONS = frozenset({"track", "playlist", "album", "artist"})


def _entry_to_search_query(title: str, artist: str | None) -> str:
    title = title.strip()
    artist_name = (artist or "").strip()
    if artist_name:
        return f"{artist_name} - {title}"[:QUERY_MAX_LEN]
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


def sync_playlist_catalog(playlist_id: str) -> list[str] | None:
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


def sync_album_catalog(album_id: str) -> list[str] | None:
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


def sync_artist_catalog(artist_id: str) -> list[str] | None:
    from spotapi.artist import Artist
    from spotapi.song import Song

    artist = Artist()
    overview = artist.get_artist(artist_id)
    artist_union = overview.get("data", {}).get("artistUnion") or {}
    profile = artist_union.get("profile")
    name = profile.get("name") if isinstance(profile, dict) else None
    artist_name = name if isinstance(name, str) else None

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


def sync_track_query(track_id: str) -> str | None:
    from spotapi.song import Song

    info = Song().get_track_info(track_id)
    track_union = info.get("data", {}).get("trackUnion")
    return _track_body_to_query(track_union)


def run_spotapi_operation_sync(operation: str, entity_id: str) -> list[str] | str | None:
    from bot.services.tls_client_alpine import (
        ensure_tls_client_alpine_patch,
        spotapi_native_supported,
    )

    if not spotapi_native_supported():
        return None
    ensure_tls_client_alpine_patch()
    if operation not in SPOTAPI_OPERATIONS:
        raise ValueError(f"unknown SpotAPI operation: {operation}")
    if operation == "track":
        return sync_track_query(entity_id)
    if operation == "playlist":
        return sync_playlist_catalog(entity_id)
    if operation == "album":
        return sync_album_catalog(entity_id)
    return sync_artist_catalog(entity_id)
