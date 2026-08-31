from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils import http_session
from bot.utils.http_session import (
    close_session,
    create_session,
    get_session,
    session_scope,
    set_session,
)


def test_get_session_returns_none_when_not_set():
    with patch.object(http_session, "_session", None):
        assert get_session() is None


def test_set_and_get_session():
    session = MagicMock()
    set_session(session)
    try:
        assert get_session() is session
    finally:
        setattr(http_session, "_session", None)


def test_get_session_clears_closed_session():
    closed_session = MagicMock()
    closed_session.closed = True
    with patch.object(http_session, "_session", closed_session):
        assert get_session() is None
        assert http_session._session is None


@pytest.mark.asyncio
async def test_close_session_closes_and_clears():
    session = MagicMock()
    session.close = AsyncMock()
    set_session(session)
    await close_session()
    session.close.assert_awaited_once()
    assert get_session() is None


@pytest.mark.asyncio
async def test_create_session_returns_client_session():
    session = create_session()
    assert session is not None
    await session.close()


@pytest.mark.asyncio
async def test_session_scope_uses_provided_open_session():
    provided = MagicMock()
    provided.closed = False
    async with session_scope(session=provided) as active:
        assert active is provided


@pytest.mark.asyncio
async def test_session_scope_uses_global_session():
    shared = MagicMock()
    shared.closed = False
    set_session(shared)
    try:
        async with session_scope() as active:
            assert active is shared
    finally:
        setattr(http_session, "_session", None)


@pytest.mark.asyncio
async def test_session_scope_temp_non_context_manager_closes_awaitable():
    class _TempSession:
        def __init__(self):
            self.close = AsyncMock()

    temp = _TempSession()
    with patch("bot.utils.http_session.create_session", return_value=temp):
        async with session_scope() as active:
            assert active is temp
    temp.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_scope_temp_non_context_manager_closes_non_awaitable():
    class _TempSession:
        def __init__(self):
            self.close = MagicMock(return_value=None)

    temp = _TempSession()
    with patch("bot.utils.http_session.create_session", return_value=temp):
        async with session_scope() as active:
            assert active is temp
    temp.close.assert_called_once()


@pytest.mark.asyncio
async def test_session_scope_temp_context_manager_uses_async_with():
    managed = MagicMock()
    managed.__aenter__ = AsyncMock(return_value=managed)
    managed.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(http_session, "_session", None),
        patch("bot.utils.http_session.create_session", return_value=managed),
    ):
        async with session_scope() as active:
            assert active is managed
    managed.__aenter__.assert_awaited_once()
    managed.__aexit__.assert_awaited_once()
