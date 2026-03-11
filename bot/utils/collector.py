"""Event collectors - wait for messages or reactions matching criteria."""

import asyncio
from typing import Callable, TypeVar

import discord

T = TypeVar("T")


async def wait_for_message(
    bot: discord.Client,
    *,
    channel_id: int | None = None,
    author_id: int | None = None,
    check: Callable[[discord.Message], bool] | None = None,
    timeout: float = 60.0,
) -> discord.Message | None:
    """Wait for a message matching criteria. Returns None on timeout."""
    future: asyncio.Future[discord.Message] = asyncio.get_event_loop().create_future()

    def predicate(m: discord.Message) -> bool:
        if m.author.bot:
            return False
        if channel_id is not None and m.channel.id != channel_id:
            return False
        if author_id is not None and m.author.id != author_id:
            return False
        if check is not None and not check(m):
            return False
        return True

    async def on_message(m: discord.Message):
        if predicate(m) and not future.done():
            future.set_result(m)

    bot.add_listener(on_message)
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        bot.remove_listener(on_message)


async def wait_for_reaction(
    bot: discord.Client,
    message_id: int,
    *,
    user_id: int | None = None,
    emoji: str | discord.Emoji | None = None,
    timeout: float = 60.0,
) -> discord.RawReactionActionEvent | None:
    """Wait for a reaction on a message. Returns None on timeout."""
    future: asyncio.Future[discord.RawReactionActionEvent] = (
        asyncio.get_event_loop().create_future()
    )

    def predicate(payload: discord.RawReactionActionEvent) -> bool:
        if payload.message_id != message_id:
            return False
        if payload.user_id == bot.user.id:
            return False
        if user_id is not None and payload.user_id != user_id:
            return False
        if emoji is not None:
            e = str(emoji) if isinstance(emoji, discord.Emoji) else emoji
            if str(payload.emoji) != e:
                return False
        return True

    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        if predicate(payload) and not future.done():
            future.set_result(payload)

    bot.add_listener(on_raw_reaction_add)
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        bot.remove_listener(on_raw_reaction_add)
