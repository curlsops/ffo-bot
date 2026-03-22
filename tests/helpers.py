from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock


def mock_interaction(
    guild_id=1,
    channel_id=2,
    user_id=3,
    guild=True,
    *,
    msg_id=None,
    user_roles=None,
    user_display_name=None,
    followup_send_return=None,
    channel=None,
    message=None,
    user=None,
    guild_get_member=None,
    **kwargs,
):
    i = MagicMock(guild_id=guild_id, channel_id=channel_id, **kwargs)
    if user is None:
        i.user = MagicMock(id=user_id)
        i.user.roles = [MagicMock(id=r) for r in (user_roles or [])]
        if user_display_name is not None:
            i.user.display_name = user_display_name
    else:
        i.user = user
    i.guild = MagicMock(id=guild_id) if guild else None
    if i.guild:
        i.guild.get_member = MagicMock(return_value=guild_get_member)
    i.channel = channel if channel is not None else MagicMock(id=channel_id)
    if message is not None:
        i.message = message
    elif msg_id is not None:
        i.message = MagicMock(id=msg_id, edit=AsyncMock())
    i.response.defer = AsyncMock()
    i.response.send_message = AsyncMock()
    i.response.edit_message = AsyncMock()
    i.followup.send = AsyncMock(return_value=followup_send_return)
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


def mock_db_ctx(conn, *, exit_result=False):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=exit_result)
    return ctx


def mock_db_pool(fetch=None, fetchrow=None, fetchval=None, execute="OK"):
    conn = mock_db_conn(fetch=fetch, fetchrow=fetchrow, fetchval=fetchval, execute=execute)

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


def db_pool_with_conn(conn, *, exit_result=False):
    pool = MagicMock()
    pool.acquire.return_value = mock_db_ctx(conn, exit_result=exit_result)
    return pool


def build_faq_bot():
    bot = MagicMock()
    bot.cache = None
    bot.notifier = None
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.db_pool.acquire = MagicMock()
    return bot


def build_quotebook_bot():
    bot = MagicMock()
    bot.cache = None
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.db_pool.acquire = MagicMock()
    return bot


def build_whitelist_bot():
    bot = MagicMock()
    bot.cache = None
    bot.notifier = MagicMock()
    bot.notifier.notify_whitelist = AsyncMock()
    bot.settings = MagicMock(feature_notify_moderation=True)
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot._register_server = AsyncMock()
    bot.minecraft_rcon = MagicMock()
    bot.minecraft_rcon._is_configured = MagicMock(return_value=True)
    bot.minecraft_rcon.whitelist_add = AsyncMock(return_value="Added")
    bot.minecraft_rcon.whitelist_remove = AsyncMock(return_value="Removed")
    bot.minecraft_rcon.whitelist_list = AsyncMock(return_value="Steve, Alex")
    bot.minecraft_rcon.whitelist_on = AsyncMock(return_value="Whitelist is now turned on")
    bot.minecraft_rcon.whitelist_off = AsyncMock(return_value="Whitelist is now turned off")
    bot.minecraft_rcon.push_master_whitelist = AsyncMock(return_value=[])
    return bot


def _embed_text(embed):
    parts = []
    if embed is None:
        return parts
    for attr in ("title", "description"):
        value = getattr(embed, attr, None)
        if isinstance(value, str):
            parts.append(value)
    footer = getattr(embed, "footer", None)
    footer_text = getattr(footer, "text", None) if footer is not None else None
    if isinstance(footer_text, str):
        parts.append(footer_text)
    for field in getattr(embed, "fields", []):
        if isinstance(field.name, str):
            parts.append(field.name)
        if isinstance(field.value, str):
            parts.append(field.value)
    return parts


def assert_followup_contains(i, substring, *, case_sensitive=False):
    call = i.followup.send.call_args
    parts = []
    parts.extend(str(arg) for arg in call.args)
    for key in ("content", "message"):
        value = call.kwargs.get(key)
        if value is not None:
            parts.append(str(value))
    parts.extend(_embed_text(call.kwargs.get("embed")))
    for embed in call.kwargs.get("embeds") or []:
        parts.extend(_embed_text(embed))
    text = " | ".join(parts)
    if not case_sensitive:
        text, substring = text.lower(), substring.lower()
    assert substring in text, f"Expected {substring!r} in followup, got: {text[:300]}"


async def invoke(cog, group_attr: str, cmd_name: str | None, i, **kwargs):
    cmd_or_group = getattr(cog, group_attr)
    if cmd_name is None:
        await cmd_or_group.callback(i, **kwargs)
    else:
        cmd = getattr(cmd_or_group, cmd_name)
        await cmd.callback(cmd_or_group, i, **kwargs)
