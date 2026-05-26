from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Awaitable, Callable, NamedTuple, Sequence, TypeVar, cast
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
from mafic import EndReason, Player, SearchType, Track, TrackEndEvent
from mafic.errors import PlayerNotConnected

from bot.auth.command_helpers import require_admin
from bot.auth.permissions import PermissionContext
from bot.services.spotify import (
    spotify_album_catalog_queries,
    spotify_artist_catalog_queries,
    spotify_playlist_catalog_queries,
    spotify_url_to_search_query,
)
from bot.services.tidal import (
    tidal_album_to_search_queries,
    tidal_mix_to_search_queries,
    tidal_playlist_to_search_queries,
    tidal_url_to_search_query,
)
from bot.utils.channel_config import (
    fetch_music_voice_channel_targets,
    get_music_voice_channel_id,
    set_music_voice_channel,
)
from bot.utils.discord_voice import (
    VOICE_DEPS_MISSING_USER_MSG,
    discord_voice_dependencies_available,
)
from bot.utils.log_context import log_command_start
from bot.utils.music import (
    EMBED_COLOR,
    _clear_queue,
    _format_duration,
    _get_queue,
    _music_embed,
    _music_status_embed,
    _order_youtube_search_tracks,
    _time_until_track,
    _track_label,
)
from bot.utils.pagination import EmbedListPaginatedView
from config.constants import Role

if TYPE_CHECKING:
    from bot.client import FFOBot

logger = logging.getLogger(__name__)

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")

QUEUE_PAGE_SIZE = 5
MAX_QUERY_LEN = 200
IDLE_LEAVE_SECONDS = 30
TRACK_PICKER_MAX = 5
PLAYLIST_FETCH_CONCURRENCY = 5
YOUTUBE_PLAYLIST_CATALOG_MAX = 2000
YOUTUBE_PLAYLIST_RESOLVE_SAMPLE = 150
MUSIC_LAZY_PREFETCH_DELAY_SEC = 0.35
CONNECTION_FAILED_MSG = "Music connection failed. Try /music leave then /music join again."


class MusicLazyTail(NamedTuple):
    search_queries: tuple[str, ...] = ()
    search_type: SearchType | None = None
    preloaded_tracks: tuple[Track, ...] = ()
    catalog_size: int = 0

    def has_work(self) -> bool:
        return bool(self.search_queries) or bool(self.preloaded_tracks)


def _playlist_intended_track_count(tracks: Sequence[Track], lazy_tail: MusicLazyTail | None) -> int:
    n = len(tracks)
    if lazy_tail is None:
        return n
    if lazy_tail.catalog_size > 0:
        return lazy_tail.catalog_size
    return n + len(lazy_tail.preloaded_tracks) + len(lazy_tail.search_queries)


class ResolvedUrl(NamedTuple):
    tracks: list[Track] | None
    playlist: bool
    resolved_query: str | None
    err: str | None
    lazy_tail: MusicLazyTail | None = None
    single_track_yt: bool = False


def _get_url_host(query: str) -> str:
    if not query.startswith(("http://", "https://")):
        return ""
    try:
        return (urlparse(query).hostname or "").lower()
    except (ValueError, TypeError):
        return ""


def _is_tidal_url(query: str) -> bool:
    h = _get_url_host(query)
    return h == "tidal.com" or h.endswith(".tidal.com")


def _is_spotify_url(query: str) -> bool:
    h = _get_url_host(query)
    return h == "spotify.com" or h.endswith(".spotify.com")


def _is_youtube_url(query: str) -> bool:
    h = _get_url_host(query)
    return h in ("youtube.com", "youtu.be") or h.endswith(".youtube.com")


def _is_allowed_music_url(query: str) -> bool:
    return _is_tidal_url(query) or _is_spotify_url(query) or _is_youtube_url(query)


def _get_voice_client(guild: discord.Guild, bot: "FFOBot"):
    return guild.voice_client or discord.utils.get(bot.voice_clients, guild=guild)


def _is_voice_or_stage(ch: discord.abc.GuildChannel | None) -> bool:
    return isinstance(ch, (discord.VoiceChannel, discord.StageChannel))


def _other_members_in_channel(channel: discord.VoiceChannel, bot_user_id: int) -> int:
    return sum(1 for m in channel.members if m.id != bot_user_id)


async def _followup_voice_connect_failed(
    i: discord.Interaction, e: RuntimeError, *, channel_id: int | None = None
) -> None:
    logger.warning(
        "Voice connect failed guild=%s channel=%s: %s",
        i.guild_id,
        channel_id,
        e,
        exc_info=True,
    )
    await i.followup.send(VOICE_DEPS_MISSING_USER_MSG, ephemeral=True)


async def reconnect_music_voice_after_ready(bot: "FFOBot") -> None:
    if not getattr(bot.settings, "feature_music", False) or not getattr(bot, "pool", None):
        return
    if not bot.db_pool:
        return
    if not discord_voice_dependencies_available():
        logger.info("Music recovery skipped (davey not available)")
        return
    targets = await fetch_music_voice_channel_targets(bot.db_pool)
    if not targets:
        logger.debug("Music recovery: no persisted voice channels")
        return
    logger.info("Music recovery: %d persisted channel(s)", len(targets))
    by_guild = {g.id: g for g in bot.guilds}
    for guild_id, channel_id in targets:
        guild = by_guild.get(guild_id)
        if not guild:
            continue
        vc = guild.voice_client
        if vc and vc.channel and vc.channel.id == channel_id:
            continue
        if vc:
            try:
                await vc.disconnect(force=True)
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.warning("Music recovery: disconnect failed guild %s: %s", guild_id, e)
        ch = guild.get_channel(channel_id)
        if not _is_voice_or_stage(ch):
            await set_music_voice_channel(bot.db_pool, guild_id, None, bot.cache)
            continue
        me = guild.me
        if me is None:
            continue
        perms = ch.permissions_for(me)
        if not (perms.connect and perms.speak):
            logger.warning("Music recovery: missing voice perms guild %s", guild_id)
            await set_music_voice_channel(bot.db_pool, guild_id, None, bot.cache)
            continue
        try:
            logger.info("Music recovery: connecting guild=%s channel=%s", guild_id, channel_id)
            await ch.connect(cls=Player, timeout=30.0, reconnect=False)
            logger.info("Music recovery: connected guild=%s channel=%s", guild_id, channel_id)
        except Exception as e:
            logger.warning(
                "Music recovery: connect failed guild %s: %s", guild_id, e, exc_info=True
            )
            await set_music_voice_channel(bot.db_pool, guild_id, None, bot.cache)


async def _play_next(player: Player) -> bool:
    queue = _get_queue(player.client, player.guild.id)
    if not queue:
        return False
    track = queue.popleft()
    try:
        await player.play(track)
    except PlayerNotConnected:
        queue.appendleft(track)
        return False
    return True


def _pop_queue_index(queue: deque[Track], idx: int) -> Track:
    queue.rotate(-idx)
    track = queue.popleft()
    queue.rotate(idx)
    return track


def _music_lazy_prefetch_tasks(bot: "FFOBot") -> dict[int, asyncio.Task[None]]:
    if not hasattr(bot, "_music_lazy_prefetch_tasks"):
        bot._music_lazy_prefetch_tasks = {}
    return cast(dict[int, asyncio.Task[None]], bot._music_lazy_prefetch_tasks)


async def _cancel_music_lazy_prefetch(bot: "FFOBot", guild_id: int) -> None:
    tasks = getattr(bot, "_music_lazy_prefetch_tasks", None)
    if not tasks or guild_id not in tasks:
        return
    t = tasks.pop(guild_id)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass


def _active_music_queue(bot: "FFOBot", guild_id: int) -> deque[Track] | None:
    queues = getattr(bot, "_music_queues", None)
    if queues is None or guild_id not in queues:
        return None
    return cast(deque[Track], queues[guild_id])


async def _music_lazy_prefetch_worker(
    bot: "FFOBot", guild_id: int, player: Player, tail: MusicLazyTail
) -> None:
    for pre in tail.preloaded_tracks:
        try:
            await asyncio.sleep(MUSIC_LAZY_PREFETCH_DELAY_SEC)
        except asyncio.CancelledError:
            return
        queue = _active_music_queue(bot, guild_id)
        if queue is None:
            return
        queue.append(pre)
    for sq in tail.search_queries:
        try:
            await asyncio.sleep(MUSIC_LAZY_PREFETCH_DELAY_SEC)
        except asyncio.CancelledError:
            return
        queue = _active_music_queue(bot, guild_id)
        if queue is None:
            return
        track = await _fetch_one_track(player, sq)
        if track:
            queue.append(track)


def _schedule_music_lazy_prefetch(
    bot: "FFOBot", guild_id: int, player: Player, tail: MusicLazyTail | None
) -> None:
    if tail is None or not tail.has_work():
        return
    tmap = _music_lazy_prefetch_tasks(bot)
    prev = tmap.pop(guild_id, None)
    if prev is not None:
        prev.cancel()

    async def _run() -> None:
        try:
            await _music_lazy_prefetch_worker(bot, guild_id, player, tail)
        finally:
            tmap.pop(guild_id, None)

    tmap[guild_id] = asyncio.create_task(_run())


async def _fetch_one_track(player: Player, query: str) -> Track | None:
    result = await player.fetch_tracks(query, search_type=SearchType.YOUTUBE)
    if result and isinstance(result, list) and result:
        return result[0]
    if result and not isinstance(result, list) and result.tracks:
        return result.tracks[0]
    return None


async def _bounded_map_ordered(
    items: list[TIn],
    worker: Callable[[TIn], Awaitable[TOut]],
    concurrency: int,
) -> list[TOut]:
    sem = asyncio.Semaphore(concurrency)

    async def run(item: TIn) -> TOut:
        async with sem:
            return await worker(item)

    return await asyncio.gather(*[run(item) for item in items])


async def _fetch_playlist_tracks(player: Player, queries: list[str]) -> list[Track]:
    results = await _bounded_map_ordered(
        queries,
        lambda sq: _fetch_one_track(player, sq),
        PLAYLIST_FETCH_CONCURRENCY,
    )
    return [t for t in results if t is not None]


async def _resolve_url_tracks(player: Player, query: str, bot: "FFOBot") -> ResolvedUrl:
    if _is_tidal_url(query):
        pq = await tidal_playlist_to_search_queries(query)
        if not pq:
            pq = await tidal_mix_to_search_queries(query)
        if not pq:
            pq = await tidal_album_to_search_queries(query)
        if pq:
            first = await _fetch_one_track(player, pq[0])
            if not first:
                return ResolvedUrl(
                    None,
                    True,
                    None,
                    "Could not resolve the first track from this Tidal link on the audio node.",
                    None,
                )
            rest = tuple(pq[1:])
            if rest:
                return ResolvedUrl(
                    [first],
                    True,
                    None,
                    None,
                    MusicLazyTail(
                        search_queries=rest,
                        search_type=SearchType.YOUTUBE,
                        catalog_size=len(pq),
                    ),
                )
            return ResolvedUrl([first], False, None, None, None)
        sq = await tidal_url_to_search_query(query)
        return (
            ResolvedUrl(None, False, sq, None, None, single_track_yt=True)
            if sq
            else ResolvedUrl(
                None, False, None, "Could not resolve Tidal link. Try searching by song name.", None
            )
        )
    if _is_spotify_url(query):
        catalog = await spotify_playlist_catalog_queries(query)
        if not catalog:
            catalog = await spotify_album_catalog_queries(query)
        if not catalog:
            catalog = await spotify_artist_catalog_queries(query)
        if catalog:
            if len(catalog) > YOUTUBE_PLAYLIST_CATALOG_MAX:
                logger.warning(
                    "Spotify catalog truncated from %s to %s tracks",
                    len(catalog),
                    YOUTUBE_PLAYLIST_CATALOG_MAX,
                )
                catalog = catalog[:YOUTUBE_PLAYLIST_CATALOG_MAX]
            first = await _fetch_one_track(player, catalog[0])
            if not first:
                return ResolvedUrl(
                    None,
                    True,
                    None,
                    "Could not resolve the first track from this Spotify link on the audio node.",
                    None,
                )
            tail = catalog[1:]
            if tail:
                return ResolvedUrl(
                    [first],
                    True,
                    None,
                    None,
                    MusicLazyTail(
                        search_queries=tuple(tail),
                        search_type=SearchType.YOUTUBE,
                        catalog_size=len(catalog),
                    ),
                )
            return ResolvedUrl([first], False, None, None, None)
        sq = await spotify_url_to_search_query(query)
        if sq:
            return ResolvedUrl(None, False, sq, None, None, single_track_yt=True)
        return ResolvedUrl(
            None,
            False,
            None,
            "Could not resolve Spotify link. Try searching by song name.",
            None,
        )
    return ResolvedUrl(None, False, None, None, None)


def _music_queue_format_row(
    row: tuple, player: Player | None, current: Track | None, queue: Sequence[Track]
) -> str:
    t, lbl, idx = row
    link = f"[{t.title}]({t.uri})" if t.uri else t.title
    return f"**#{lbl}** {link} ({_format_duration(t.length)}) · {_time_until_track(player, current, queue, idx)}"


def _MusicQueueView(
    player: Player | None, current: Track | None, queue: Sequence[Track]
) -> EmbedListPaginatedView:
    rows: list[tuple[Track, str, int]] = ([(current, "Now", 0)] if current else []) + [
        (t, str(i), i) for i, t in enumerate(queue, 1)
    ]

    def fmt(r):
        return _music_queue_format_row(r, player, current, queue)

    return EmbedListPaginatedView(
        rows, fmt, "🎵 Music Queue", per_page=QUEUE_PAGE_SIZE, color=EMBED_COLOR
    )


class _ResumeView(discord.ui.View):
    def __init__(self, player: Player, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.player = player

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.success, row=0)
    async def resume_btn(self, i: discord.Interaction, _: discord.ui.Button):
        if self.player.paused:
            await self.player.resume()
            for c in self.children:
                c.disabled = True
            await i.response.edit_message(embed=_music_embed("▶️ Resumed", ""), view=self)
        else:
            await i.response.defer()


class TrackPickerView(discord.ui.View):
    def __init__(self, tracks: list[Track], player: Player, bot: "FFOBot", timeout: float = 120):
        super().__init__(timeout=timeout)
        self.tracks, self.player, self.bot = tracks[:TRACK_PICKER_MAX], player, bot
        self._chosen = False
        for i, t in enumerate(self.tracks):
            b = discord.ui.Button(
                label=_track_label(t, i + 1),
                style=discord.ButtonStyle.secondary,
                custom_id=f"music:pick:{i}",
                row=i // 5,
            )
            b.callback = self._make_callback(i)
            self.add_item(b)

    def _make_callback(self, idx: int):
        async def cb(i: discord.Interaction):
            if self._chosen:
                await i.response.defer(ephemeral=True)
                return
            self._chosen = True
            track = self.tracks[idx]
            if self.player.current:
                q = _get_queue(self.bot, self.player.guild.id)
                start_pos = len(q) + 1
                q.append(track)
                desc = f"**{track.title}** at #{start_pos}."
                resume = _ResumeView(self.player) if self.player.paused else None
                await i.response.edit_message(embed=_music_embed("📥 Queued", desc), view=resume)
                return
            try:
                await self.player.play(track)
            except PlayerNotConnected:
                await i.response.send_message(CONNECTION_FAILED_MSG, ephemeral=True)
                return
            await i.response.edit_message(
                embed=_music_embed("🎵 Playing", f"▶️ **{track.title}**"), view=None
            )

        return cb


async def _check_voice_pool(
    i: discord.Interaction,
) -> tuple[discord.VoiceChannel, discord.VoiceClient | None] | None:
    if not i.user.voice or not i.user.voice.channel:
        await i.followup.send("Join a voice channel first.", ephemeral=True)
        return None
    if not discord_voice_dependencies_available():
        await i.followup.send(VOICE_DEPS_MISSING_USER_MSG, ephemeral=True)
        return None
    if not i.client.pool:
        await i.followup.send("Music is not enabled.", ephemeral=True)
        return None
    guild = i.guild
    if not guild:
        return None
    return i.user.voice.channel, guild.voice_client


async def _ensure_player(i: discord.Interaction) -> tuple[Player, discord.VoiceChannel] | None:
    r = await _check_voice_pool(i)
    if r is None:
        return None
    ch, vc = r
    player = vc if isinstance(vc, Player) else None
    if not player:
        try:
            await ch.connect(cls=Player)
        except TimeoutError:
            await i.followup.send("Voice connection timed out. Try again.", ephemeral=True)
            return None
        except RuntimeError as e:
            await _followup_voice_connect_failed(i, e, channel_id=ch.id)
            return None
        player = i.guild.voice_client
    if player.channel.id != ch.id:
        await i.followup.send("Join the same voice channel as the bot.", ephemeral=True)
        return None
    return player, ch


@app_commands.guild_only()
class MusicGroup(app_commands.Group):
    def __init__(self, cog: "MusicCommands"):
        super().__init__(name="music", description="Music playback via Lavalink")
        self.cog = cog

    @app_commands.command(name="join", description="Join your voice channel")
    async def join(self, i: discord.Interaction):
        await i.response.defer(ephemeral=False)
        log_command_start(logger, "music", "music join", i)
        r = await _check_voice_pool(i)
        if r is None:
            return
        ch, vc = r
        if vc and vc.channel:
            if vc.channel.id == ch.id:
                await i.followup.send("Already in your channel.")
            else:
                await i.followup.send(
                    f"Bot is currently in {vc.channel.mention}. Use /music leave first.",
                    ephemeral=True,
                )
            return
        try:
            await ch.connect(cls=Player)
        except TimeoutError:
            await i.followup.send("Voice connection timed out. Try again.", ephemeral=True)
            return
        except RuntimeError as e:
            await _followup_voice_connect_failed(i, e, channel_id=ch.id)
            return
        await i.followup.send(embed=_music_embed("🎵 Joined", f"Connected to {ch.mention}."))

    @app_commands.command(name="play", description="Play a track (URL or search query)")
    @app_commands.describe(
        query=(
            "YouTube URL (incl. playlists). "
            "Tidal track/album/playlist/mix. "
            "Spotify track/album/playlist/artist (public catalog via SpotAPI, YouTube playback). "
            "Or plain search text."
        ),
        force_next="Play next in queue (mod+ only)",
    )
    async def play(self, i: discord.Interaction, query: str, force_next: bool = False):
        await i.response.defer(ephemeral=False)
        log_command_start(logger, "music", "music play", i)
        query = query.strip()[:MAX_QUERY_LEN]
        if not query:
            await i.followup.send("Provide a URL or search query.", ephemeral=True)
            return
        r = await _ensure_player(i)
        if r is None:
            return
        player, _ch = r
        bot = i.client
        is_url = query.startswith(("http://", "https://"))
        search_type = None if is_url else SearchType.YOUTUBE
        tracks = None
        playlist = False
        lazy_tail: MusicLazyTail | None = None
        single_track_yt = False
        if is_url and _is_allowed_music_url(query):
            ru = await _resolve_url_tracks(player, query, bot)
            if ru.err:
                await i.followup.send(ru.err, ephemeral=True)
                return
            if ru.resolved_query:
                query = ru.resolved_query
                search_type = SearchType.YOUTUBE
            tracks = ru.tracks
            playlist = ru.playlist
            lazy_tail = ru.lazy_tail
            single_track_yt = ru.single_track_yt
        if tracks is None:
            result = await player.fetch_tracks(query, search_type=search_type)
            if result is None:
                await i.followup.send("No results found.", ephemeral=True)
                return
            tracks = result if isinstance(result, list) else result.tracks
            if search_type is None and len(tracks) > 1 and _is_youtube_url(query):
                catalog = list(tracks)[:YOUTUBE_PLAYLIST_CATALOG_MAX]
                k = min(YOUTUBE_PLAYLIST_RESOLVE_SAMPLE, len(catalog))
                head = catalog[:k]
                tracks = [head[0]]
                lazy_tail = MusicLazyTail(
                    preloaded_tracks=tuple(head[1:]),
                    catalog_size=len(catalog),
                )
                playlist = True
            elif not isinstance(result, list) and search_type is None and len(tracks) > 1:
                lt = list(tracks)
                tracks = [lt[0]]
                lazy_tail = MusicLazyTail(
                    preloaded_tracks=tuple(lt[1:]),
                    catalog_size=len(lt),
                )
                playlist = True
        if not tracks:
            await i.followup.send("No tracks found.", ephemeral=True)
            return
        if single_track_yt and len(tracks) > 1:
            if search_type == SearchType.YOUTUBE:
                tracks = [_order_youtube_search_tracks(list(tracks))[0]]
            else:
                tracks = [tracks[0]]
        if len(tracks) > 1 and not playlist and search_type == SearchType.YOUTUBE:
            tracks = _order_youtube_search_tracks(list(tracks))
        if force_next:
            ctx = PermissionContext(
                server_id=i.guild_id or 0, user_id=i.user.id, command_name="music play"
            )
            if not await bot.permission_checker.check_role(ctx, Role.MODERATOR):
                await i.followup.send(
                    "Moderator or higher required for force play next.", ephemeral=True
                )
                return
        guild_id = i.guild_id or 0
        queue = _get_queue(bot, guild_id)
        if not playlist and len(tracks) > 1:
            lines = [
                f"**{n + 1}.** {getattr(t, 'author', '') or ''} – {t.title}"
                for n, t in enumerate(tracks[:TRACK_PICKER_MAX])
            ]
            await i.followup.send(
                embed=_music_embed("🎵 Pick a track", "\n".join(lines)),
                view=TrackPickerView(tracks, player, bot),
                ephemeral=True,
            )
            return
        if player.current:
            count = _playlist_intended_track_count(tracks, lazy_tail)
            if force_next:
                for t in reversed(tracks):
                    queue.appendleft(t)
                start_pos = 1
            else:
                start_pos = len(queue) + 1
                queue.extend(tracks)
            pr = f"#{start_pos}–#{start_pos + count - 1}" if count > 1 else f"#{start_pos}"
            desc = (
                f"Added {count} track{'s' if count != 1 else ''} at {pr}."
                if playlist
                else f"**{tracks[0].title}** at #{start_pos}"
                + (
                    f" (+{count - 1} more at #{start_pos + 1}–#{start_pos + count - 1})"
                    if count > 1
                    else ""
                )
                + "."
            )
            if force_next:
                desc += " (playing next)"
            send_kw = {"embed": _music_embed("📥 Queued", desc)}
            if player.paused:
                send_kw["view"] = _ResumeView(player)
            await i.followup.send(**send_kw)
            if lazy_tail and lazy_tail.has_work():
                _schedule_music_lazy_prefetch(bot, guild_id, player, lazy_tail)
        else:
            try:
                await player.play(tracks[0])
            except PlayerNotConnected:
                await i.followup.send(CONNECTION_FAILED_MSG, ephemeral=True)
                return
            if playlist and len(tracks) > 1:
                queue.extend(tracks[1:])
            queued_after = _playlist_intended_track_count(tracks, lazy_tail) - 1
            desc = f"▶️ **{tracks[0].title}**" + (
                f"\n📥 +{queued_after} queued" if playlist and queued_after > 0 else ""
            )
            await i.followup.send(embed=_music_embed("🎵 Playing", desc))
            if lazy_tail and lazy_tail.has_work():
                _schedule_music_lazy_prefetch(bot, guild_id, player, lazy_tail)

    @app_commands.command(name="leave", description="Disconnect from voice")
    async def leave(self, i: discord.Interaction):
        await i.response.defer(ephemeral=False)
        log_command_start(logger, "music", "music leave", i)
        vc = _get_voice_client(i.guild, i.client)
        if not vc:
            bot = i.client
            if bot.db_pool:
                stale = await get_music_voice_channel_id(
                    bot.db_pool, i.guild_id or 0, getattr(bot, "cache", None)
                )
                if stale:
                    await set_music_voice_channel(
                        bot.db_pool, i.guild_id or 0, None, getattr(bot, "cache", None)
                    )
                    await i.followup.send(
                        "No active voice session (for example after a restart). "
                        "Cleared stored voice channel for this server.",
                        ephemeral=True,
                    )
                    return
            await i.followup.send("Not in a voice channel.", ephemeral=True)
            return
        name = vc.channel.name if vc.channel else "voice"
        await _cancel_music_lazy_prefetch(i.client, vc.guild.id)
        _clear_queue(i.client, i.guild_id)
        await _cancel_leave_task(_get_leave_tasks(i.client), i.guild_id)
        await vc.disconnect()
        await i.followup.send(embed=_music_embed("👋 Left", f"Disconnected from {name}."))

    async def _player_or_nothing(
        self, i: discord.Interaction, msg: str = "Nothing playing."
    ) -> Player | None:
        p = i.guild.voice_client
        if not p or not isinstance(p, Player):
            await i.followup.send(msg, ephemeral=True)
            return None
        return p

    async def _pause_resume(self, i: discord.Interaction, pause: bool):
        await i.response.defer(ephemeral=False)
        if (p := await self._player_or_nothing(i)) is None:
            return
        if pause == p.paused:
            await i.followup.send(
                embed=_music_embed("⏸️ Already paused" if pause else "▶️ Not paused", "")
            )
            return
        await (p.pause() if pause else p.resume())
        title = p.current.title if p.current else "Track"
        await i.followup.send(
            embed=_music_embed("⏸️ Paused" if pause else "▶️ Resumed", f"**{title}**")
        )

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, i: discord.Interaction):
        await self._pause_resume(i, True)

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, i: discord.Interaction):
        await self._pause_resume(i, False)

    @app_commands.command(
        name="status", description="Show voice channel, current track, and progress"
    )
    async def status(self, i: discord.Interaction):
        await i.response.defer(ephemeral=False)
        if not i.client.pool:
            await i.followup.send("Music is not enabled.", ephemeral=True)
            return
        guild = i.guild
        if not guild:
            return
        vc = _get_voice_client(guild, i.client)
        if not vc or not isinstance(vc, Player):
            await i.followup.send(
                embed=_music_embed(
                    "🎵 Music status",
                    "The bot is not connected to a voice channel in this server.",
                ),
                ephemeral=True,
            )
            return
        ch = vc.channel
        ch_ref = ch.mention if ch else "a voice channel"
        await i.followup.send(embed=_music_status_embed(vc, ch_ref, paused=vc.paused))

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, i: discord.Interaction):
        await i.response.defer(ephemeral=False)
        if (p := await self._player_or_nothing(i)) is None:
            return
        skipped = p.current.title if p.current else None
        await p.stop()
        if await _play_next(p):
            next_t = p.current.title if p.current else None
            await i.followup.send(
                embed=_music_embed(
                    "⏭️ Skipped", f"Skipped **{skipped}**.\n▶️ Now playing: **{next_t}**"
                )
            )
        else:
            await i.followup.send(
                embed=_music_embed(
                    "⏭️ Skipped", f"Skipped **{skipped}**." if skipped else "Skipped."
                )
            )

    @app_commands.command(name="clear-queue", description="[Admin] Clear the queue")
    @app_commands.default_permissions(administrator=True)
    async def clear_queue(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        if not await require_admin(i, "music clear-queue", self.cog.bot):
            return
        q = _get_queue(i.client, i.guild_id)
        if not q:
            await i.followup.send(
                embed=_music_embed("🎵 Clear Queue", "Queue is already empty."), ephemeral=True
            )
            return
        await _cancel_music_lazy_prefetch(i.client, i.guild_id or 0)
        _clear_queue(i.client, i.guild_id)
        await i.followup.send(
            embed=_music_embed("🎵 Queue Cleared", f"Removed {len(q)} track(s)."), ephemeral=True
        )

    @app_commands.command(
        name="force-play", description="[Admin] Force play a track at queue position"
    )
    @app_commands.describe(position="Queue position (1 = next in queue)")
    @app_commands.default_permissions(administrator=True)
    async def force_play(self, i: discord.Interaction, position: int):
        await i.response.defer(ephemeral=False)
        if not await require_admin(i, "music force-play", self.cog.bot):
            return
        if position < 1:
            await i.followup.send("Position must be at least 1.", ephemeral=True)
            return
        if (p := await self._player_or_nothing(i, "Not in a voice channel.")) is None:
            return
        q = _get_queue(i.client, i.guild_id)
        idx = position - 1
        if idx >= len(q):
            await i.followup.send(
                f"No track at position {position}. Queue has {len(q)} item(s).", ephemeral=True
            )
            return
        track = _pop_queue_index(q, idx)
        if p.current:
            q.appendleft(p.current)
            await p.stop()
        try:
            await p.play(track)
        except PlayerNotConnected:
            q.appendleft(track)
            await i.followup.send(CONNECTION_FAILED_MSG, ephemeral=True)
            return
        await i.followup.send(embed=_music_embed("🎵 Force Playing", f"▶️ **{track.title}**"))

    @app_commands.command(name="queue", description="Show the queue")
    async def queue_cmd(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        log_command_start(logger, "music", "music queue", i)
        p = i.guild.voice_client
        q = _get_queue(i.client, i.guild_id)
        cur = p.current if (p and isinstance(p, Player)) else None
        if not cur and not q:
            await i.followup.send(embed=_music_embed("🎵 Queue", "Queue is empty."), ephemeral=True)
            return
        v = _MusicQueueView(p, cur, q)
        await i.followup.send(embed=v._format_page(), view=v, ephemeral=True)


def _get_leave_tasks(bot: FFOBot) -> dict[int, asyncio.Task[None]]:
    if not hasattr(bot, "_music_leave_tasks"):
        bot._music_leave_tasks = {}
    return cast(dict[int, asyncio.Task[None]], bot._music_leave_tasks)


async def _cancel_leave_task(tasks: dict[int, asyncio.Task], guild_id: int) -> None:
    if guild_id in tasks:
        tasks[guild_id].cancel()
        try:
            await tasks[guild_id]
        except asyncio.CancelledError:
            pass
        del tasks[guild_id]


class MusicCommands(commands.Cog):
    def __init__(self, bot: FFOBot):
        self.bot = bot
        self.music_group = MusicGroup(self)
        self.bot.tree.add_command(self.music_group)

    @commands.Cog.listener("on_voice_state_update")
    async def _on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if (
            getattr(self.bot.settings, "feature_music", False)
            and self.bot.db_pool
            and self.bot.user
            and member.id == self.bot.user.id
        ):
            if after.channel and _is_voice_or_stage(after.channel):
                await set_music_voice_channel(
                    self.bot.db_pool, member.guild.id, after.channel.id, self.bot.cache
                )
            elif before.channel and not after.channel:
                await set_music_voice_channel(
                    self.bot.db_pool, member.guild.id, None, self.bot.cache
                )

        if not self.bot.pool or not self.bot.user:
            return
        tasks = _get_leave_tasks(self.bot)
        for vc in self.bot.voice_clients:
            if not vc.channel or not vc.guild:
                continue
            bot_channel = vc.channel
            guild_id = vc.guild.id
            affected = (before.channel and before.channel.id == bot_channel.id) or (
                after.channel and after.channel.id == bot_channel.id
            )
            if not affected:
                continue
            others = _other_members_in_channel(bot_channel, self.bot.user.id)
            if others > 0:
                await _cancel_leave_task(tasks, guild_id)
            else:

                async def _leave_after_idle() -> None:
                    await asyncio.sleep(IDLE_LEAVE_SECONDS)
                    vc = _get_voice_client(bot_channel.guild, self.bot)
                    if vc and vc.channel and vc.channel.id == bot_channel.id:
                        if _other_members_in_channel(vc.channel, self.bot.user.id) == 0:
                            await _cancel_music_lazy_prefetch(self.bot, guild_id)
                            _clear_queue(self.bot, guild_id)
                            await vc.disconnect()
                            logger.info("Left voice channel %s (idle)", vc.channel.name)
                    tasks.pop(guild_id, None)

                await _cancel_leave_task(tasks, guild_id)
                tasks[guild_id] = asyncio.create_task(_leave_after_idle())

    @commands.Cog.listener("on_track_end")
    async def _on_track_end(self, event: TrackEndEvent) -> None:
        if event.reason not in (EndReason.FINISHED, EndReason.LOAD_FAILED):
            return
        if await _play_next(event.player):
            logger.debug("Playing next track in queue for guild %s", event.player.guild.id)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command("music")


async def setup(bot: FFOBot) -> None:
    await bot.add_cog(MusicCommands(bot))
