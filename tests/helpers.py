from unittest.mock import AsyncMock, MagicMock


def mock_interaction(guild_id=1, channel_id=2, user_id=3, guild=True):
    i = MagicMock(guild_id=guild_id, channel_id=channel_id)
    i.user = MagicMock(id=user_id)
    i.guild = MagicMock() if guild else None
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.response.edit_message = AsyncMock()
    i.followup.send = AsyncMock()
    i.client = MagicMock()
    return i


def mock_db_conn(fetch=None, fetchrow=None, fetchval=None, execute=None):
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
