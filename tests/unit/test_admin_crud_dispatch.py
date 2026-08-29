from unittest.mock import AsyncMock

import pytest

from bot.utils.admin_crud_dispatch import dispatch_operation
from tests.helpers import mock_interaction


@pytest.mark.asyncio
async def test_dispatch_calls_matching_handler():
    i = mock_interaction()
    add_handler = AsyncMock()
    handlers = {"add": add_handler, "remove": AsyncMock()}

    await dispatch_operation(i, "add", handlers)

    add_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_defers_ephemeral_by_default():
    i = mock_interaction()

    await dispatch_operation(i, "add", {"add": AsyncMock()})

    i.response.defer.assert_awaited_once_with(ephemeral=True)


@pytest.mark.asyncio
async def test_dispatch_unknown_operation_is_noop():
    i = mock_interaction()
    handler = AsyncMock()

    await dispatch_operation(i, "nope", {"add": handler})

    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_ephemeral_override():
    i = mock_interaction()

    await dispatch_operation(i, "add", {"add": AsyncMock()}, ephemeral=False)

    i.response.defer.assert_awaited_once_with(ephemeral=False)
