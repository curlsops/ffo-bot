from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock


def mock_interaction(
    guild_id=1,
    channel_id=2,
    user_id=3,
    guild=True,
    *,
    channel=None,
    message=None,
    user=None,
    guild_get_member=None,
    **kwargs,
):
    i = MagicMock(guild_id=guild_id, channel_id=channel_id, **kwargs)
    i.user = user if user is not None else MagicMock(id=user_id)
    i.guild = MagicMock(id=guild_id) if guild else None
    if i.guild:
        i.guild.get_member = MagicMock(return_value=guild_get_member)
    i.channel = channel if channel is not None else MagicMock(id=channel_id)
    if message is not None:
        i.message = message
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.response.edit_message = AsyncMock()
    i.followup.send = AsyncMock()
    i.client = MagicMock()
    return i


def mock_user(user_id: int, name: str = "user"):
    u = MagicMock()
    u.id = user_id
    u.name = name
    u.mention = f"<@{user_id}>"
    return u


def mock_db_conn(fetch=None, fetchrow=None, fetchval=None, execute="OK"):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=fetch if fetch is not None else [])
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetchval = AsyncMock(return_value=fetchval)
    conn.execute = AsyncMock(return_value=execute)
    return conn


def mock_db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def mock_db_pool(fetch=None, fetchrow=None, fetchval=None, execute="OK"):
    conn = mock_db_conn(fetch=fetch, fetchrow=fetchrow, fetchval=fetchval, execute=execute)

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


def assert_followup_contains(i, substring, *, case_sensitive=False):
    text = str(i.followup.send.call_args)
    if not case_sensitive:
        text, substring = text.lower(), substring.lower()
    assert substring in text, f"Expected {substring!r} in followup, got: {text[:200]}"


async def invoke(cog, group_attr: str, cmd_name: str, i, **kwargs):
    group = getattr(cog, group_attr)
    cmd = getattr(group, cmd_name)
    await cmd.callback(group, i, **kwargs)
