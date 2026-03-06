import logging
import re
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

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


async def spotify_url_to_search_query(url: str) -> str | None:
    if SPOTIFY_PLAYLIST_PATTERN.search(url) or SPOTIFY_ALBUM_PATTERN.search(url):
        return None
    if not SPOTIFY_TRACK_PATTERN.search(url):
        return None
    oembed_url = f"{SPOTIFY_OEMBED}?url={quote(url, safe='')}"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
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
    return title if title else None
