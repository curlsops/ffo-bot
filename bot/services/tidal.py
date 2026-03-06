import html
import logging
import re

import aiohttp

logger = logging.getLogger(__name__)

TIDAL_API_BASE = "https://api.tidal.com/v1"
TIDAL_TOKEN = "gsFXkJqGrUNoYMQPZe4k3WKwijnrp8iGSwn3bApe"
TIDAL_PLAYLIST_PAGE_SIZE = 100
TIDAL_PLAYLIST_MAX_TRACKS = 50

TIDAL_TRACK_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:tidal\.com|listen\.tidal\.com)/"
    r"(?:browse/)?(?:track|album)/(\d+)(?:/[^/]*)?",
    re.IGNORECASE,
)
TIDAL_PLAYLIST_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:tidal\.com|listen\.tidal\.com)/"
    r"(?:browse/)?playlist/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12})",
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
        return html.unescape(f"{artist_name} - {title}".strip())[:200]
    return html.unescape(title.strip())[:200]


async def tidal_playlist_to_search_queries(url: str) -> list[str] | None:
    m = TIDAL_PLAYLIST_PATTERN.search(url)
    if not m:
        return None
    uuid = m.group(1)
    queries: list[str] = []
    offset = 0
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            while len(queries) < TIDAL_PLAYLIST_MAX_TRACKS:
                api_url = (
                    f"{TIDAL_API_BASE}/playlists/{uuid}/tracks"
                    f"?countryCode=US&limit={TIDAL_PLAYLIST_PAGE_SIZE}&offset={offset}"
                )
                async with session.get(api_url, headers=TIDAL_API_HEADERS) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                items = data.get("items") or []
                if not items:
                    break
                for item in items:
                    q = _track_to_search_query(item)
                    if q:
                        queries.append(q)
                    if len(queries) >= TIDAL_PLAYLIST_MAX_TRACKS:
                        break
                if len(items) < TIDAL_PLAYLIST_PAGE_SIZE:
                    break
                offset += TIDAL_PLAYLIST_PAGE_SIZE
    except aiohttp.ClientError as e:
        logger.debug("Tidal playlist fetch failed for %s: %s", url, e)
        return None
    return queries if queries else None


async def tidal_url_to_search_query(url: str) -> str | None:
    if TIDAL_PLAYLIST_PATTERN.search(url):
        return None
    if not TIDAL_TRACK_PATTERN.search(url):
        return None
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
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
