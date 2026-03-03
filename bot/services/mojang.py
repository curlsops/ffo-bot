"""Mojang/Minecraft Services API client for username validation and profile lookup.

Uses api.minecraftservices.com (primary) with api.mojang.com and NameMC fallbacks.
Returns UUID and canonical username for whitelist storage.
"""

import logging
import re
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile/lookup/name/{username}"
FALLBACK_URL = "https://api.mojang.com/minecraft/profile/lookup/name/{username}"
NAMEMC_PROFILE_URL = "https://namemc.com/profile/{username}"

# Regex to extract UUID from NameMC profile page meta tags or data attributes
NAMEMC_UUID_PATTERN = re.compile(r'data-id="([a-f0-9-]{32,36})"', re.IGNORECASE)
NAMEMC_TITLE_PATTERN = re.compile(r"<title>([^<|]+)", re.IGNORECASE)


def _format_uuid(uuid_raw: str) -> str:
    u = str(uuid_raw).replace("-", "")
    if len(u) == 32:
        return f"{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}"
    return str(uuid_raw)


async def _get_profile_from_mojang(username: str) -> Optional[tuple[str, str]]:
    for url_template in (PROFILE_URL, FALLBACK_URL):
        url = url_template.format(username=username)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
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
                        continue
                    logger.warning("Mojang API unexpected status %s for %s", resp.status, username)
                    return None
        except aiohttp.ClientError as e:
            logger.debug("Mojang API request failed for %s: %s", username, e)
            continue
    return None


async def _get_profile_from_namemc(username: str) -> Optional[tuple[str, str]]:
    url = NAMEMC_PROFILE_URL.format(username=username)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0 (compatible; FFOBot/1.0)"},
            ) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
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
    except aiohttp.ClientError as e:
        logger.debug("NameMC request failed for %s: %s", username, e)
        return None


async def get_profile(username: str) -> Optional[tuple[str, str]]:
    """Fetch Minecraft profile (UUID, canonical name) from Mojang APIs with NameMC fallback.

    Args:
        username: Minecraft username (3-16 chars, alphanumeric + underscore)

    Returns:
        (uuid, name) if username exists, None otherwise. UUID is dashed format.
    """
    result = await _get_profile_from_mojang(username)
    if result:
        return result
    namemc_result = await _get_profile_from_namemc(username)
    if namemc_result and namemc_result[0]:
        logger.debug("Got profile from NameMC fallback for %s", username)
        return namemc_result
    return None


async def username_exists(username: str) -> bool:
    """Check if a Minecraft username exists via Mojang APIs with NameMC fallback."""
    result = await _get_profile_from_mojang(username)
    if result:
        return True
    namemc_result = await _get_profile_from_namemc(username)
    if namemc_result:
        return True
    return False
