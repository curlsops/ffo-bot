import html
import logging
import re

import aiohttp

from bot.utils.http_session import get_session, session_scope
from bot.utils.telemetry import trace_span

logger = logging.getLogger(__name__)

TIDAL_API_BASE = "https://api.tidal.com/v1"
TIDAL_TOKEN = "gsFXkJqGrUNoYMQPZe4k3WKwijnrp8iGSwn3bApe"
TIDAL_PLAYLIST_PAGE_SIZE = 100

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
) -> tuple[list[str], int | None] | None:
    with trace_span(
        "tidal.catalog_page",
        feature="music",
        attributes={"tidal.path": path, "tidal.offset": offset},
    ):
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
            queries: list[str] = [q for item in items if (q := _track_to_search_query(item))]
            if len(items) < TIDAL_PLAYLIST_PAGE_SIZE:
                return queries, None
            return queries, offset + TIDAL_PLAYLIST_PAGE_SIZE
        except aiohttp.ClientError as e:
            logger.debug("Tidal fetch failed for %s: %s", path, e)
            return None


async def _tidal_catalog_start(
    pattern: re.Pattern[str],
    path_fmt: str,
    url: str,
) -> tuple[list[str], str | None, int] | None:
    m = pattern.search(url)
    if not m:
        return None
    entity_id = m.group(1)
    kind = "playlist"
    if "mix" in path_fmt:
        kind = "mix"
    elif "album" in path_fmt:
        kind = "album"
    with trace_span(
        "tidal.catalog_start",
        feature="music",
        attributes={"tidal.kind": kind, "tidal.entity_id": entity_id},
    ):
        path = path_fmt.format(uuid=entity_id)
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


async def tidal_album_catalog_start(url: str) -> tuple[list[str], str | None, int] | None:
    return await _tidal_catalog_start(TIDAL_ALBUM_PATTERN, "albums/{uuid}/tracks", url)


async def tidal_fetch_catalog_page(path: str, offset: int) -> tuple[list[str], int | None] | None:
    async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
        return await _fetch_catalog_page(session, path, offset)


async def tidal_url_to_search_query(url: str) -> str | None:
    if (
        TIDAL_PLAYLIST_PATTERN.search(url)
        or TIDAL_MIX_PATTERN.search(url)
        or TIDAL_ALBUM_PATTERN.search(url)
    ):
        return None
    track_match = TIDAL_TRACK_PATTERN.search(url)
    if not track_match:
        return None
    track_id = track_match.group(1)
    with trace_span(
        "tidal.track_query",
        feature="music",
        attributes={"tidal.track_id": track_id},
    ):
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
