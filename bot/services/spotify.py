import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

import aiohttp
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.services.spotapi_subprocess import run_spotapi_subprocess
from bot.services.spotapi_sync import QUERY_MAX_LEN, run_spotapi_operation_sync
from bot.utils.http_session import get_session, session_scope
from bot.utils.log_context import log_debug
from bot.utils.telemetry import trace_span

logger = logging.getLogger(__name__)

SPOTIFY_OEMBED = "https://open.spotify.com/oembed"
TIMEOUT = aiohttp.ClientTimeout(total=10)


class _SpotapiRuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    spotapi_use_subprocess: bool = Field(default=True)
    spotapi_subprocess_timeout_sec: float = Field(default=90.0, ge=5.0, le=300.0)


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

_spotapi_runtime: tuple[bool, float] | None = None


def reset_spotapi_runtime_config() -> None:
    global _spotapi_runtime
    _spotapi_runtime = None


def _spotapi_config() -> tuple[bool, float]:
    global _spotapi_runtime
    if _spotapi_runtime is None:
        s = _SpotapiRuntimeSettings()
        _spotapi_runtime = (s.spotapi_use_subprocess, s.spotapi_subprocess_timeout_sec)
    return _spotapi_runtime


async def _run_spotapi_operation(operation: str, entity_id: str) -> list[str] | str | None:
    log_debug(
        logger,
        "spotify spotapi call operation=%s id=%s",
        operation,
        entity_id,
        feature="spotify",
    )
    use_subprocess, timeout_sec = _spotapi_config()
    with trace_span(
        "spotify.spotapi",
        feature="spotify",
        attributes={"spotify.operation": operation},
    ):
        if use_subprocess:
            return await run_spotapi_subprocess(operation, entity_id, timeout_sec=timeout_sec)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: run_spotapi_operation_sync(operation, entity_id)
        )


async def _spotify_catalog_from_url(
    pattern: re.Pattern[str],
    operation: str,
    url: str,
) -> list[str] | None:
    match = pattern.search(url)
    if not match:
        return None
    entity_id = match.group(1)
    try:
        with trace_span(
            "spotify.catalog",
            feature="spotify",
            attributes={"spotify.entity": operation},
        ):
            result = await _run_spotapi_operation(operation, entity_id)
            return result if isinstance(result, list) else None
    except Exception as e:
        logger.debug("SpotAPI %s fetch failed for %s: %s", operation, url, e)
        return None


async def spotify_playlist_catalog_queries(url: str) -> list[str] | None:
    return await _spotify_catalog_from_url(SPOTIFY_PLAYLIST_PATTERN, "playlist", url)


async def spotify_album_catalog_queries(url: str) -> list[str] | None:
    return await _spotify_catalog_from_url(SPOTIFY_ALBUM_PATTERN, "album", url)


async def spotify_artist_catalog_queries(url: str) -> list[str] | None:
    return await _spotify_catalog_from_url(SPOTIFY_ARTIST_PATTERN, "artist", url)


async def _fetch_oembed_json(
    session: aiohttp.ClientSession, oembed_url: str
) -> dict[str, Any] | None:
    async with session.get(oembed_url) as resp:
        if resp.status != 200:
            return None
        payload = await resp.json()
        return payload if isinstance(payload, dict) else None


async def _fetch_spotify_oembed_json(url: str) -> dict[str, Any] | None:
    oembed_url = f"{SPOTIFY_OEMBED}?url={quote(url, safe='')}"
    log_debug(logger, "spotify oembed fetch url=%s", url, feature="spotify")
    try:
        with trace_span("spotify.oembed", feature="spotify"):
            async with session_scope(timeout=TIMEOUT, session=get_session()) as session:
                return await _fetch_oembed_json(session, oembed_url)
    except aiohttp.ClientError as e:
        logger.debug("Spotify oEmbed fetch failed for %s: %s", url, e)
        return None


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
        result = await _run_spotapi_operation("track", track_id)
        query = result if isinstance(result, str) else None
    except Exception as e:
        logger.debug("SpotAPI track fetch failed for %s: %s", url, e)
        query = None
    if query:
        return query
    data = await _fetch_spotify_oembed_json(url)
    if data is None:
        return None
    title = data.get("title")
    if not title or not isinstance(title, str):
        return None
    title = title.strip()[:QUERY_MAX_LEN]
    return title or None
