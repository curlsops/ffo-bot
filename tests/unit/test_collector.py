import asyncio
from unittest.mock import MagicMock

import pytest

from bot.utils.collector import wait_for_message, wait_for_reaction


@pytest.mark.asyncio
async def test_wait_for_message_timeout():
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 1
    result = await wait_for_message(bot, timeout=0.01)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_message_success():
    bot = MagicMock()
    bot.user = MagicMock(id=1)
    listeners = []

    def add_listener(fn):
        listeners.append(fn)

    def remove_listener(fn):
        if fn in listeners:
            listeners.remove(fn)

    bot.add_listener = add_listener
    bot.remove_listener = remove_listener

    msg = MagicMock()
    msg.author.bot = False
    msg.channel.id = 5
    msg.author.id = 10

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(msg)

    task = asyncio.create_task(dispatch())
    result = await wait_for_message(bot, channel_id=5, author_id=10, timeout=1.0)
    await task
    assert result is msg


@pytest.mark.asyncio
async def test_wait_for_reaction_timeout():
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 1
    result = await wait_for_reaction(bot, message_id=123, timeout=0.01)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_reaction_success():
    bot = MagicMock()
    bot.user = MagicMock(id=1)
    listeners = []

    def add_listener(fn):
        listeners.append(fn)

    def remove_listener(fn):
        if fn in listeners:
            listeners.remove(fn)

    bot.add_listener = add_listener
    bot.remove_listener = remove_listener

    payload = MagicMock()
    payload.message_id = 99
    payload.user_id = 10
    payload.emoji = type("Emoji", (), {"__str__": lambda s: "👍"})()

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(payload)

    task = asyncio.create_task(dispatch())
    result = await wait_for_reaction(bot, message_id=99, user_id=10, emoji="👍", timeout=1.0)
    await task
    assert result is payload


def _collector_bot(listeners):
    bot = MagicMock()
    bot.user = MagicMock(id=1)

    def add_listener(fn):
        listeners.append(fn)

    def remove_listener(fn):
        if fn in listeners:
            listeners.remove(fn)

    bot.add_listener = add_listener
    bot.remove_listener = remove_listener
    return bot


@pytest.mark.asyncio
async def test_wait_for_message_rejects_bot_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    bot_msg = MagicMock()
    bot_msg.author.bot = True
    bot_msg.channel.id = 5
    bot_msg.author.id = 10
    good_msg = MagicMock()
    good_msg.author.bot = False
    good_msg.channel.id = 5
    good_msg.author.id = 10

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(bot_msg)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good_msg)

    task = asyncio.create_task(dispatch())
    result = await wait_for_message(bot, channel_id=5, author_id=10, timeout=1.0)
    await task
    assert result is good_msg


@pytest.mark.asyncio
async def test_wait_for_message_rejects_wrong_channel_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    wrong_ch = MagicMock()
    wrong_ch.author.bot = False
    wrong_ch.channel.id = 999
    wrong_ch.author.id = 10
    good_msg = MagicMock()
    good_msg.author.bot = False
    good_msg.channel.id = 5
    good_msg.author.id = 10

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(wrong_ch)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good_msg)

    task = asyncio.create_task(dispatch())
    result = await wait_for_message(bot, channel_id=5, author_id=10, timeout=1.0)
    await task
    assert result is good_msg


@pytest.mark.asyncio
async def test_wait_for_message_rejects_wrong_author_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    wrong_author = MagicMock()
    wrong_author.author.bot = False
    wrong_author.channel.id = 5
    wrong_author.author.id = 999
    good_msg = MagicMock()
    good_msg.author.bot = False
    good_msg.channel.id = 5
    good_msg.author.id = 10

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(wrong_author)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good_msg)

    task = asyncio.create_task(dispatch())
    result = await wait_for_message(bot, channel_id=5, author_id=10, timeout=1.0)
    await task
    assert result is good_msg


@pytest.mark.asyncio
async def test_wait_for_message_rejects_check_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    bad_msg = MagicMock()
    bad_msg.author.bot = False
    bad_msg.channel.id = 5
    bad_msg.author.id = 10
    good_msg = MagicMock()
    good_msg.author.bot = False
    good_msg.channel.id = 5
    good_msg.author.id = 10
    good_msg.content = "yes"

    def check(m):
        return "yes" in getattr(m, "content", "")

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(bad_msg)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good_msg)

    task = asyncio.create_task(dispatch())
    result = await wait_for_message(bot, channel_id=5, author_id=10, check=check, timeout=1.0)
    await task
    assert result is good_msg


@pytest.mark.asyncio
async def test_wait_for_reaction_rejects_wrong_message_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    wrong_msg = MagicMock()
    wrong_msg.message_id = 1
    wrong_msg.user_id = 10
    wrong_msg.emoji = type("E", (), {"__str__": lambda s: "👍"})()
    good = MagicMock()
    good.message_id = 99
    good.user_id = 10
    good.emoji = type("E", (), {"__str__": lambda s: "👍"})()

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(wrong_msg)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good)

    task = asyncio.create_task(dispatch())
    result = await wait_for_reaction(bot, message_id=99, user_id=10, emoji="👍", timeout=1.0)
    await task
    assert result is good


@pytest.mark.asyncio
async def test_wait_for_reaction_rejects_bot_user_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    bot.user.id = 1
    bot_reaction = MagicMock()
    bot_reaction.message_id = 99
    bot_reaction.user_id = 1
    bot_reaction.emoji = type("E", (), {"__str__": lambda s: "👍"})()
    good = MagicMock()
    good.message_id = 99
    good.user_id = 10
    good.emoji = type("E", (), {"__str__": lambda s: "👍"})()

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(bot_reaction)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good)

    task = asyncio.create_task(dispatch())
    result = await wait_for_reaction(bot, message_id=99, user_id=10, emoji="👍", timeout=1.0)
    await task
    assert result is good


@pytest.mark.asyncio
async def test_wait_for_reaction_rejects_wrong_user_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    wrong_user = MagicMock()
    wrong_user.message_id = 99
    wrong_user.user_id = 999
    wrong_user.emoji = type("E", (), {"__str__": lambda s: "👍"})()
    good = MagicMock()
    good.message_id = 99
    good.user_id = 10
    good.emoji = type("E", (), {"__str__": lambda s: "👍"})()

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(wrong_user)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good)

    task = asyncio.create_task(dispatch())
    result = await wait_for_reaction(bot, message_id=99, user_id=10, emoji="👍", timeout=1.0)
    await task
    assert result is good


@pytest.mark.asyncio
async def test_wait_for_reaction_rejects_wrong_emoji_then_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    wrong_emoji = MagicMock()
    wrong_emoji.message_id = 99
    wrong_emoji.user_id = 10
    wrong_emoji.emoji = type("E", (), {"__str__": lambda s: "👎"})()
    good = MagicMock()
    good.message_id = 99
    good.user_id = 10
    good.emoji = type("E", (), {"__str__": lambda s: "👍"})()

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(wrong_emoji)
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(good)

    task = asyncio.create_task(dispatch())
    result = await wait_for_reaction(bot, message_id=99, user_id=10, emoji="👍", timeout=1.0)
    await task
    assert result is good


@pytest.mark.asyncio
async def test_wait_for_reaction_no_emoji_filter_accepts():
    listeners = []
    bot = _collector_bot(listeners)
    payload = MagicMock()
    payload.message_id = 99
    payload.user_id = 10
    payload.emoji = type("E", (), {"__str__": lambda s: "👍"})()

    async def dispatch():
        await asyncio.sleep(0.01)
        for fn in listeners:
            await fn(payload)

    task = asyncio.create_task(dispatch())
    result = await wait_for_reaction(bot, message_id=99, user_id=10, emoji=None, timeout=1.0)
    await task
    assert result is payload
