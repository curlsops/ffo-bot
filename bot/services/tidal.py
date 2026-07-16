import html
import logging
import re

import aiohttp

from bot.utils.http_session import get_session, session_scope

logger = logging.getLogger(__name__)

TIDAL_API_BASE = "https://api.tidal.com/v1"
TIDAL_TOKEN = "gsFXkJqGrUNoYMQPZe4k3WKwijnrp8iGSwn3bApe"
TIDAL_PLAYLIST_PAGE_SIZE = 100
TIDAL_PLAYLIST_CATALOG_MAX = 2000
TIDAL_PLAYLIST_RESOLVE_SAMPLE = 50

TIDAL_TRACK_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:tidal\.com|listen\.tidal\.com)/" r"(?:browse/)?track/(\d+)(?:/[^/]*)?",
    re.IGNORECASE,
)
TIDAL_ALBUM_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:tidal\.com|listen\.tidal\.com)/" r"(?:browse/)?album/(\d+)(?:/[^/]*)?",
    re.IGNORECASE,
)
TIDAL_PLAYLIST_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:tidal\.com|listen\.tidal\.com)/"
    r"(?:browse/)?playlist/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12})",
    re.IGNORECASE,
)
TIDAL_MIX_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:tidal\.com|listen\.tidal\.com)/"
    r"(?:browse/)?mix/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12})",
    re.IGNORECASE,
)
OG_TITLE_PATTERN = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
OG_TITLE_ALT_PATTERN = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
    re.IGNORECASE,
)

TIMEOUT = aiohttp.ClientTimeout(total=10)
USER_AGENT = "Mozilla/5.0 (compatible; DiscordBot/1.0)"
TIDAL_API_HEADERS = {
    "x-tidal-token": TIDAL_TOKEN,
    "User-Agent": USER_AGENT,
}


def _sample_catalog_queries(queries: list[str]) -> list[str]:
    if not queries:
        return []
    k = min(TIDAL_PLAYLIST_RESOLVE_SAMPLE, len(queries))
    return queries[:k]


def _track_to_search_query(item: dict) -> str | None:
    title = item.get("title")
    artist = item.get("artist") or (item.get("artists") or [{}])[0]
    artist_name = artist.get("name") if isinstance(artist, dict) else None
    if not title:
        return None
    if artist_name:
        return str(html.unescape(f"{artist_name} - {title}".strip())[:200])
    return str(html.unescape(str(title).strip())[:200])


async def _fetch_catalog_page(
    session: aiohttp.ClientSession,
    path: str,
    offset: int,
    *,
    max_tracks: int | None = None,
) -> tuple[list[str], int | None] | None:
    cap = TIDAL_PLAYLIST_CATALOG_MAX if max_tracks is None else max_tracks
    try:
        api_url = (
            f"{TIDAL_API_BASE}/{path}"
            f"?countryCode=US&limit={TIDAL_PLAYLIST_PAGE_SIZE}&offset={offset}"
        )
        async with session.get(api_url, headers=TIDAL_API_HEADERS) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        items = data.get("items") or []
        if not items:
            return [], None
        queries: list[str] = []
        for item in items:
            q = _track_to_search_query(item)
            if q:
                queries.append(q)
            if len(queries) >= cap:
                break
        if len(queries) >= cap:
            return queries, None
        if len(items) < TIDAL_PLAYLIST_PAGE_SIZE:
            return queries, None
        return queries, offset + TIDAL_PLAYLIST_PAGE_SIZE
    except aiohttp.ClientError as e:
        logger.debug("Tidal fetch failed for %s: %s", path, e)
        return None


async def _fetch_catalog_from_api(
    session: aiohttp.ClientSession,
    path: str,
    *,
    max_tracks: int | None = None,
) -> list[str] | None:
    cap = TIDAL_PLAYLIST_CATALOG_MAX if max_tracks is None else max_tracks
    queries: list[str] = []
    offset = 0
    while len(queries) < cap:
        page = await _fetch_catalog_page(session, path, offset, max_tracks=cap - len(queries))
        if page is None:
            return None
        batch, next_offset = page
        if not batch and next_offset is None:
            break
        queries.extend(batch)
        if len(queries) >= cap or next_offset is None:
            break
        offset = next_offset
    return queries or None


async def _tidal_catalog_start(
    pattern: re.Pattern[str],
    path_fmt: str,
    url: str,
) -> tuple[list[str], str | None, int] | None:
    m = pattern.search(url)
    if not m:
        return None
    path = path_fmt.format(uuid=m.group(1))
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        page = await _fetch_catalog_page(session, path, 0)
    if page is None:
        return None
    queries, next_offset = page
    if not queries:
        return None
    cont_path = path if next_offset is not None else None
    return queries, cont_path, next_offset or 0


async def tidal_playlist_catalog_start(url: str) -> tuple[list[str], str | None, int] | None:
    return await _tidal_catalog_start(TIDAL_PLAYLIST_PATTERN, "playlists/{uuid}/tracks", url)


async def tidal_mix_catalog_start(url: str) -> tuple[list[str], str | None, int] | None:
    return await _tidal_catalog_start(TIDAL_MIX_PATTERN, "mixes/{uuid}/tracks", url)


async def tidal_fetch_catalog_page(path: str, offset: int) -> tuple[list[str], int | None] | None:
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        return await _fetch_catalog_page(session, path, offset)


async def tidal_playlist_to_search_queries(url: str) -> list[str] | None:
    m = TIDAL_PLAYLIST_PATTERN.search(url)
    if not m:
        return None
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        catalog = await _fetch_catalog_from_api(session, f"playlists/{m.group(1)}/tracks")
    return catalog


async def tidal_mix_to_search_queries(url: str) -> list[str] | None:
    m = TIDAL_MIX_PATTERN.search(url)
    if not m:
        return None
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        catalog = await _fetch_catalog_from_api(session, f"mixes/{m.group(1)}/tracks")
    return catalog


async def tidal_album_to_search_queries(url: str) -> list[str] | None:
    m = TIDAL_ALBUM_PATTERN.search(url)
    if not m:
        return None
    album_id = m.group(1)
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        catalog = await _fetch_catalog_from_api(session, f"albums/{album_id}/tracks")
    if not catalog:
        return None
    return catalog


async def tidal_url_to_search_query(url: str) -> str | None:
    if (
        TIDAL_PLAYLIST_PATTERN.search(url)
        or TIDAL_MIX_PATTERN.search(url)
        or TIDAL_ALBUM_PATTERN.search(url)
    ):
        return None
    if not TIDAL_TRACK_PATTERN.search(url):
        return None
    try:
        async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
            async with session.get(url, headers={"User-Agent": USER_AGENT}) as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
    except aiohttp.ClientError as e:
        logger.debug("Tidal fetch failed for %s: %s", url, e)
        return None
    for pattern in (OG_TITLE_PATTERN, OG_TITLE_ALT_PATTERN):
        m = pattern.search(body)
        if m:
            title = html.unescape(m.group(1).strip())
            if title and len(title) <= 200:
                return title
    return None
