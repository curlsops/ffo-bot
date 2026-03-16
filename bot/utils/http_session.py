import logging
from contextlib import asynccontextmanager
from inspect import isawaitable

import aiohttp

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession | None:
    global _session
    if _session is not None and getattr(_session, "closed", False) is True:
        _session = None
    return _session


def set_session(session: aiohttp.ClientSession) -> None:
    global _session
    _session = session


async def close_session() -> None:
    global _session
    if _session:
        await _session.close()
        _session = None


def create_session(timeout: aiohttp.ClientTimeout | None = None) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=timeout or _DEFAULT_TIMEOUT)


@asynccontextmanager
async def session_scope(
    timeout: aiohttp.ClientTimeout | None = None,
    session: aiohttp.ClientSession | None = None,
):
    if session is not None and getattr(session, "closed", False) is not True:
        yield session
        return

    session = get_session()
    if session is not None:
        yield session
        return

    temp_session = create_session(timeout=timeout)
    if hasattr(temp_session, "__aenter__") and hasattr(temp_session, "__aexit__"):
        async with temp_session as managed_session:
            yield managed_session
        return

    try:
        yield temp_session
    finally:
        close_result = temp_session.close()
        if isawaitable(close_result):
            await close_result
