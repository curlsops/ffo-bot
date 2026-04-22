from collections import defaultdict, deque
from itertools import islice
from typing import TYPE_CHECKING, Iterable, Sequence, cast

import discord
from mafic import Player, Track

if TYPE_CHECKING:
    from bot.client import FFOBot

EMBED_COLOR = 0x9B59B6
TRACK_PICKER_LABEL_MAX = 50

_YT_SEARCH_POSITIVE = (
    "official music video",
    "official video",
    "official audio",
    "(official",
    "[official",
    " - official",
    " official ",
)
_YT_SEARCH_NEGATIVE = (
    " reaction",
    " reacts",
    " cover",
    "karaoke",
    "nightcore",
    "8d audio",
    " slowed ",
    " mashup",
    " tiktok",
    "read description",
)


def _youtube_search_track_score(track: Track) -> int:
    title = (track.title or "").lower()
    author = (getattr(track, "author", None) or "").lower()
    blob = f" {title} {author} "
    score = 0
    for hint in _YT_SEARCH_POSITIVE:
        if hint in blob:
            score += 55
            break
    if "vevo" in title or "vevo" in author:
        score += 28
    for bad in _YT_SEARCH_NEGATIVE:
        if bad in blob:
            score -= 20
    ln = int(getattr(track, "length", None) or 0)
    if 0 < ln < 45_000:
        score -= 14
    return max(score, -80)


def _order_youtube_search_tracks(tracks: Sequence[Track]) -> list[Track]:
    if len(tracks) < 2:
        return list(tracks)
    return [
        t
        for _, t in sorted(
            enumerate(tracks),
            key=lambda it: (-_youtube_search_track_score(it[1]), it[0]),
        )
    ]


def _format_duration(ms: int) -> str:
    if ms <= 0:
        return "live"
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _get_queue(bot: "FFOBot", guild_id: int) -> deque[Track]:
    if not hasattr(bot, "_music_queues"):
        bot._music_queues = defaultdict(lambda: deque())
    return cast(deque[Track], bot._music_queues[guild_id])


def _clear_queue(bot: "FFOBot", guild_id: int) -> None:
    queues = getattr(bot, "_music_queues", None)
    if queues is not None and guild_id in queues:
        del queues[guild_id]


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
    player: Player | None, current: Track | None, queue: Iterable[Track], idx: int
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
    for queued_track in islice(queue, idx - 1):
        cum += _ms(getattr(queued_track, "length", None))
    return "in " + _format_duration(cum)
