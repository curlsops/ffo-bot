from collections import defaultdict, deque
from itertools import islice
from typing import TYPE_CHECKING, Iterable, Sequence, cast
from urllib.parse import parse_qs, urlparse

import discord
from mafic import Player, Track

if TYPE_CHECKING:
    from bot.client import FFOBot

EMBED_COLOR = 0x9B59B6
TRACK_PICKER_LABEL_MAX = 50
_STREAM_LENGTH_THRESHOLD_MS = 7 * 24 * 60 * 60 * 1000

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


def _youtube_video_id(uri: str | None, identifier: str) -> str | None:
    def _yt_id_shape(s: str) -> bool:
        return len(s) == 11 and all(c.isalnum() or c in "-_" for c in s)

    if uri and uri.startswith(("http://", "https://")):
        try:
            p = urlparse(uri)
        except (ValueError, TypeError):
            p = None
        if p and p.hostname:
            host = p.hostname.lower()
            if host == "youtu.be":
                seg = (p.path or "").strip("/").split("/")[0]
                if seg:
                    return seg
            if host in ("youtube.com", "www.youtube.com") or host.endswith(".youtube.com"):
                qs = parse_qs(p.query or "")
                vals = qs.get("v")
                if vals and vals[0]:
                    return vals[0]
                parts = [x for x in (p.path or "").split("/") if x]
                if len(parts) >= 2 and parts[0] == "embed":
                    return parts[1]
                if len(parts) >= 2 and parts[0] == "shorts":
                    return parts[1]
    if identifier and _yt_id_shape(identifier):
        return identifier
    return None


def _track_is_stream(track: Track, length_ms: int) -> bool:
    if getattr(track, "stream", False):
        return True
    return length_ms <= 0 or length_ms > _STREAM_LENGTH_THRESHOLD_MS


def _track_listen_url(track: Track) -> str | None:
    uri = getattr(track, "uri", None)
    uri_str = uri if isinstance(uri, str) else None
    if uri_str and uri_str.startswith(("http://", "https://")):
        return uri_str
    src = (getattr(track, "source", None) or "").lower()
    ident = getattr(track, "identifier", "") or ""
    if src == "youtube" or (uri_str and "youtube" in uri_str.lower()):
        vid = _youtube_video_id(uri_str, ident)
        if vid:
            return f"https://www.youtube.com/watch?v={vid}"
    return uri_str if uri_str else None


def _track_status_thumbnail_url(track: Track) -> str | None:
    art = getattr(track, "artwork_url", None) or None
    if isinstance(art, str) and art:
        return art
    uri = getattr(track, "uri", None)
    uri_str = uri if isinstance(uri, str) else None
    ident = getattr(track, "identifier", "") or ""
    vid = _youtube_video_id(uri_str, ident)
    if vid:
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return None


def _music_status_embed(
    player: Player,
    channel_ref: str,
    *,
    paused: bool,
) -> discord.Embed:
    cur = player.current
    pause_note = "\n⏸️ Paused." if paused else ""
    if not cur:
        desc = f"Connected to {channel_ref}.{pause_note}\nNothing playing right now."
        return discord.Embed(title="🎵 Music status", description=desc.strip(), color=EMBED_COLOR)

    author = getattr(cur, "author", None) or ""
    head = f"**{author} – {cur.title}**" if author else f"**{cur.title}**"
    listen = _track_listen_url(cur)
    if listen and ("youtube.com" in listen or "youtu.be" in listen):
        head += f"\n[Open on YouTube]({listen})"
    elif listen:
        head += f"\n[Open track]({listen})"

    pos = _ms(getattr(player, "position", None))
    length_ms = _ms(getattr(cur, "length", None))
    if _track_is_stream(cur, length_ms):
        timing = f"**Position:** {_format_duration(pos)}\n**Length:** live stream"
    else:
        pos_clamped = min(pos, length_ms)
        left = max(0, length_ms - pos_clamped)
        timing = (
            f"**Time left:** {_format_duration(left)}\n"
            f"**Total length:** {_format_duration(length_ms)}\n"
            f"**Elapsed:** {_format_duration(pos_clamped)}"
        )

    desc = f"Playing in {channel_ref}.\n\n{head}\n\n{timing}{pause_note}"
    emb = discord.Embed(title="🎵 Now playing", description=desc.strip(), color=EMBED_COLOR)
    thumb = _track_status_thumbnail_url(cur)
    if thumb:
        emb.set_thumbnail(url=thumb)
    return emb


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
