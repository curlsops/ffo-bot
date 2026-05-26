import logging
import re

import aiohttp

from bot.utils.http_session import get_session as _get_session
from bot.utils.http_session import session_scope
from bot.utils.telemetry import trace_span

get_session = _get_session

logger = logging.getLogger(__name__)

PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile/lookup/name/{username}"
FALLBACK_URL = "https://api.mojang.com/minecraft/profile/lookup/name/{username}"
SESSION_PROFILE_BY_UUID_URL = (
    "https://sessionserver.mojang.com/session/minecraft/profile/{uuid_no_dashes}"
)
BATCH_URL = "https://api.minecraftservices.com/minecraft/profile/lookup/bulk/byname"
BATCH_FALLBACK_URL = "https://api.mojang.com/profiles/minecraft"
NAMEMC_PROFILE_URL = "https://namemc.com/profile/{username}"

BATCH_SIZE = 10

NAMEMC_UUID_PATTERN = re.compile(r'data-id="([a-f0-9-]{32,36})"', re.IGNORECASE)
NAMEMC_TITLE_PATTERN = re.compile(r"<title>([^<|]+)", re.IGNORECASE)


def _format_uuid(uuid_raw: str) -> str:
    u = str(uuid_raw).replace("-", "")
    if len(u) == 32:
        return f"{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}"
    return str(uuid_raw)


class _MojangRetry(Exception):
    pass


async def _get_profile_from_mojang(username: str) -> tuple[str, str] | None:
    for url_template in (PROFILE_URL, FALLBACK_URL):
        url = url_template.format(username=username)
        try:
            async with session_scope(session=get_session()) as session:
                async with session.get(url) as resp:
                    return await _parse_mojang_resp(resp, username)
        except _MojangRetry:
            continue
        except aiohttp.ClientError as e:
            logger.debug("Mojang API request failed for %s: %s", username, e)
            continue
    return None


async def _parse_mojang_resp(resp, username: str) -> tuple[str, str] | None:
    if resp.status == 200:
        data = await resp.json()
        uuid_raw = data.get("id") or data.get("uuid")
        name = data.get("name", username)
        if uuid_raw:
            return (_format_uuid(uuid_raw), name)
        return None
    if resp.status == 404:
        return None
    if resp.status in (403, 429):
        logger.debug("Mojang API %s for %s, trying fallback", resp.status, username)
        raise _MojangRetry()
    logger.warning("Mojang API unexpected status %s for %s", resp.status, username)
    return None


async def _get_profile_from_namemc(username: str) -> tuple[str | None, str] | None:
    url = NAMEMC_PROFILE_URL.format(username=username)
    timeout = aiohttp.ClientTimeout(total=10)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FFOBot/1.0)"}
    try:
        async with session_scope(session=get_session()) as session:
            async with session.get(url, timeout=timeout, headers=headers) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
                return _parse_namemc_html(html, username)
    except aiohttp.ClientError as e:
        logger.debug("NameMC request failed for %s: %s", username, e)
        return None


def _parse_namemc_html(html: str, username: str) -> tuple[str | None, str] | None:
    if "Profile Not Found" in html or "This page does not exist" in html:
        return None
    uuid_match = NAMEMC_UUID_PATTERN.search(html)
    title_match = NAMEMC_TITLE_PATTERN.search(html)
    if uuid_match:
        uuid_raw = uuid_match.group(1)
        name = title_match.group(1).strip() if title_match else username
        return (_format_uuid(uuid_raw), name)
    if title_match and title_match.group(1).strip().lower() != "namemc":
        return (None, title_match.group(1).strip())
    return None


def _uuid_without_dashes(uuid_raw: str) -> str:
    return re.sub(r"[^a-fA-F0-9]", "", str(uuid_raw)).lower()


async def get_profile_by_uuid(uuid_str: str) -> tuple[str, str] | None:
    u = _uuid_without_dashes(uuid_str)
    if len(u) != 32:
        return None
    url = SESSION_PROFILE_BY_UUID_URL.format(uuid_no_dashes=u)
    with trace_span("mojang.profile_by_uuid", feature="whitelist"):
        try:
            async with session_scope(session=get_session()) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        id_raw = data.get("id")
                        name = data.get("name")
                        if id_raw and name:
                            return (_format_uuid(id_raw), name)
                        return None
                    if resp.status in (204, 404):
                        return None
                    logger.debug("Session server profile lookup %s for uuid", resp.status)
                    return None
        except aiohttp.ClientError as e:
            logger.debug("Session server request failed: %s", e)
            return None


async def get_profile(username: str) -> tuple[str, str] | None:
    with trace_span("mojang.profile", feature="whitelist"):
        return await _get_profile_impl(username)


async def _get_profile_impl(username: str) -> tuple[str, str] | None:
    result = await _get_profile_from_mojang(username)
    if result:
        return result
    namemc_result = await _get_profile_from_namemc(username)
    if namemc_result and namemc_result[0] is not None:
        logger.debug("Got profile from NameMC fallback for %s", username)
        return (namemc_result[0], namemc_result[1])
    return None


async def username_exists(username: str) -> bool:
    result = await _get_profile_from_mojang(username)
    if result:
        return True
    namemc_result = await _get_profile_from_namemc(username)
    if namemc_result:
        return True
    return False


async def get_profiles_batch(usernames: list[str]) -> dict[str, tuple[str, str]]:
    if not usernames:
        return {}

    with trace_span(
        "mojang.profiles_batch",
        feature="whitelist",
        attributes={"mojang.batch_count": len(usernames)},
    ):
        results: dict[str, tuple[str, str]] = {}
        remaining = list(usernames)

        for batch_start in range(0, len(remaining), BATCH_SIZE):
            batch = remaining[batch_start : batch_start + BATCH_SIZE]
            batch_results = await _batch_lookup(batch)
            results.update(batch_results)

        return results


async def _batch_lookup(usernames: list[str]) -> dict[str, tuple[str, str]]:
    results: dict[str, tuple[str, str]] = {}
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {"Content-Type": "application/json"}

    for url in (BATCH_URL, BATCH_FALLBACK_URL):
        try:
            async with session_scope(timeout=timeout, session=get_session()) as session:
                async with session.post(
                    url, json=usernames, headers=headers, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for profile in data:
                            uuid_raw = profile.get("id") or profile.get("uuid")
                            name = profile.get("name", "")
                            if uuid_raw and name:
                                results[name.lower()] = (_format_uuid(uuid_raw), name)
                        return results
                    if resp.status in (403, 429):
                        logger.debug("Batch API %s, trying fallback", resp.status)
                        continue
                    logger.warning("Batch API unexpected status %s", resp.status)
                    continue
        except aiohttp.ClientError as e:  # pragma: no branch
            logger.debug("Batch API request failed: %s", e)
            continue

    return results
