import asyncio
import base64
import logging
import random
import re
import time
from urllib.parse import quote

import aiohttp

from bot.utils.http_session import get_session as _get_session
from bot.utils.http_session import session_scope

get_session = _get_session

logger = logging.getLogger(__name__)

SPOTIFY_OEMBED = "https://open.spotify.com/oembed"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_PLAYLIST_PAGE_SIZE = 50
SPOTIFY_PLAYLIST_CATALOG_MAX = 2000
SPOTIFY_PLAYLIST_RESOLVE_SAMPLE = 50
TIMEOUT = aiohttp.ClientTimeout(total=10)

_SPOTIFY_TOKEN_CACHE: tuple[str, float] | None = None
_SPOTIFY_TOKEN_TTL = 3500
_SPOTIFY_TOKEN_LOCK = asyncio.Lock()

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


async def spotify_url_to_search_query(url: str) -> str | None:
    if SPOTIFY_PLAYLIST_PATTERN.search(url) or SPOTIFY_ALBUM_PATTERN.search(url):
        return None
    if not SPOTIFY_TRACK_PATTERN.search(url):
        return None
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
    title = title.strip()[:200]
    return title or None


async def _get_spotify_token(client_id: str, client_secret: str) -> str | None:
    global _SPOTIFY_TOKEN_CACHE
    now = time.monotonic()
    if _SPOTIFY_TOKEN_CACHE and (now - _SPOTIFY_TOKEN_CACHE[1]) < _SPOTIFY_TOKEN_TTL:
        return _SPOTIFY_TOKEN_CACHE[0]
    async with _SPOTIFY_TOKEN_LOCK:
        now = time.monotonic()
        if _SPOTIFY_TOKEN_CACHE and (now - _SPOTIFY_TOKEN_CACHE[1]) < _SPOTIFY_TOKEN_TTL:
            return _SPOTIFY_TOKEN_CACHE[0]
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        try:
            async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
                async with session.post(
                    SPOTIFY_TOKEN_URL,
                    headers={
                        "Authorization": f"Basic {creds}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except aiohttp.ClientError as e:
            logger.debug("Spotify token fetch failed: %s", e)
            return None
        token = data.get("access_token")
        if not token or not isinstance(token, str):
            return None
        _SPOTIFY_TOKEN_CACHE = (token, time.monotonic())
        return str(token)


def _sample_catalog_queries(queries: list[str]) -> list[str]:
    if not queries:
        return []
    k = min(SPOTIFY_PLAYLIST_RESOLVE_SAMPLE, len(queries))
    return random.sample(queries, k)


def _spotify_track_to_search_query(item: dict) -> str | None:
    track = item.get("track")
    body = track if isinstance(track, dict) else item
    if not body or body.get("is_local"):
        return None
    name = body.get("name")
    if not name or not isinstance(name, str):
        return None
    artists = body.get("artists") or []
    artist_name = None
    if artists and isinstance(artists[0], dict):
        artist_name = artists[0].get("name")
    if artist_name:
        return str(f"{artist_name} - {name}".strip()[:200])
    return str(name.strip()[:200])


async def spotify_playlist_catalog_queries(
    url: str, client_id: str | None, client_secret: str | None
) -> list[str] | None:
    if not client_id or not client_secret:
        return None
    m = SPOTIFY_PLAYLIST_PATTERN.search(url)
    if not m:
        return None
    playlist_id = m.group(1)
    token = await _get_spotify_token(client_id, client_secret)
    if not token:
        return None
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        catalog = await _spotify_playlist_fetch_catalog(session, playlist_id, token)
    return catalog


async def spotify_playlist_to_search_queries(
    url: str, client_id: str | None, client_secret: str | None
) -> list[str] | None:
    catalog = await spotify_playlist_catalog_queries(url, client_id, client_secret)
    if not catalog:
        return None
    return _sample_catalog_queries(catalog)


async def spotify_album_catalog_queries(
    url: str, client_id: str | None, client_secret: str | None
) -> list[str] | None:
    if not client_id or not client_secret:
        return None
    m = SPOTIFY_ALBUM_PATTERN.search(url)
    if not m:
        return None
    album_id = m.group(1)
    token = await _get_spotify_token(client_id, client_secret)
    if not token:
        return None
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        catalog = await _spotify_album_fetch_catalog(session, album_id, token)
    return catalog


async def spotify_album_to_search_queries(
    url: str, client_id: str | None, client_secret: str | None
) -> list[str] | None:
    catalog = await spotify_album_catalog_queries(url, client_id, client_secret)
    if not catalog:
        return None
    return _sample_catalog_queries(catalog)


async def _spotify_playlist_fetch_catalog(
    session: aiohttp.ClientSession, playlist_id: str, token: str
) -> list[str] | None:
    queries: list[str] = []
    offset = 0
    try:
        while len(queries) < SPOTIFY_PLAYLIST_CATALOG_MAX:
            api_url = (
                f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks"
                f"?limit={SPOTIFY_PLAYLIST_PAGE_SIZE}&offset={offset}"
            )
            async with session.get(
                api_url,
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status == 401:
                    global _SPOTIFY_TOKEN_CACHE
                    _SPOTIFY_TOKEN_CACHE = None
                if resp.status != 200:
                    return None
                data = await resp.json()
            items = data.get("items") or []
            if not items:
                break
            for item in items:
                q = _spotify_track_to_search_query(item)
                if q:
                    queries.append(q)
                if len(queries) >= SPOTIFY_PLAYLIST_CATALOG_MAX:
                    break
            if len(items) < SPOTIFY_PLAYLIST_PAGE_SIZE:
                break
            offset += SPOTIFY_PLAYLIST_PAGE_SIZE
    except aiohttp.ClientError as e:
        logger.debug("Spotify playlist fetch failed: %s", e)
        return None
    return queries or None


async def _spotify_album_fetch_catalog(
    session: aiohttp.ClientSession, album_id: str, token: str
) -> list[str] | None:
    queries: list[str] = []
    offset = 0
    try:
        while len(queries) < SPOTIFY_PLAYLIST_CATALOG_MAX:
            api_url = (
                f"{SPOTIFY_API_BASE}/albums/{album_id}/tracks"
                f"?limit={SPOTIFY_PLAYLIST_PAGE_SIZE}&offset={offset}"
            )
            async with session.get(
                api_url,
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status == 401:
                    global _SPOTIFY_TOKEN_CACHE
                    _SPOTIFY_TOKEN_CACHE = None
                if resp.status != 200:
                    return None
                data = await resp.json()
            items = data.get("items") or []
            if not items:
                break
            for item in items:
                q = _spotify_track_to_search_query(item)
                if q:
                    queries.append(q)
                if len(queries) >= SPOTIFY_PLAYLIST_CATALOG_MAX:
                    break
            if len(items) < SPOTIFY_PLAYLIST_PAGE_SIZE:
                break
            offset += SPOTIFY_PLAYLIST_PAGE_SIZE
    except aiohttp.ClientError as e:
        logger.debug("Spotify album fetch failed: %s", e)
        return None
    return queries or None
