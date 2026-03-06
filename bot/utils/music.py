from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from mafic import Player, Track

if TYPE_CHECKING:
    from bot.client import FFOBot

EMBED_COLOR = 0x9B59B6
TRACK_PICKER_LABEL_MAX = 50


def _format_duration(ms: int) -> str:
    if ms <= 0:
        return "live"
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _get_queue(bot: "FFOBot", guild_id: int) -> list[Track]:
    if not hasattr(bot, "_music_queues"):
        bot._music_queues = defaultdict(list)
    return bot._music_queues[guild_id]


def _clear_queue(bot: "FFOBot", guild_id: int) -> None:
    if hasattr(bot, "_music_queues") and guild_id in bot._music_queues:
        del bot._music_queues[guild_id]


def _music_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=EMBED_COLOR)


def _track_label(track: Track, i: int) -> str:
    author = getattr(track, "author", None) or ""
    label = " – ".join(p for p in ([author, track.title] if author else [track.title]) if p)
    return (f"{i}. {label}" if label else f"{i}. {track.title}")[:TRACK_PICKER_LABEL_MAX]


def _ms(v) -> int:
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _time_until_track(
    player: Player | None, current: Track | None, queue: list[Track], idx: int
) -> str:
    if idx == 0:
        if not current or not player:
            return "—"
        left = max(
            0, _ms(getattr(current, "length", None)) - _ms(getattr(player, "position", None))
        )
        return _format_duration(left) + " left"
    cum = (
        max(0, _ms(getattr(current, "length", None)) - _ms(getattr(player, "position", None)))
        if (current and player)
        else 0
    )
    for i in range(idx - 1):
        cum += _ms(getattr(queue[i], "length", None))
    return "in " + _format_duration(cum)
