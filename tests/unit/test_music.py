import asyncio
from collections import deque
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest
from mafic import EndReason, Playlist, SearchType
from mafic.errors import PlayerNotConnected, TrackLoadException

from bot.commands.music import (
    CONNECTION_FAILED_MSG,
    PLAYLIST_FETCH_CONCURRENCY,
    YOUTUBE_PLAYLIST_CATALOG_MAX,
    YOUTUBE_PLAYLIST_RESOLVE_SAMPLE,
    MusicCommands,
    MusicLazyTail,
    ResolvedUrl,
    TrackPickerView,
    _cancel_leave_task,
    _cancel_music_lazy_prefetch,
    _check_voice_pool,
    _clear_queue,
    _ensure_player,
    _fetch_one_track,
    _fetch_one_track_spotify,
    _fetch_playlist_tracks,
    _format_duration,
    _get_leave_tasks,
    _get_queue,
    _get_url_host,
    _is_spotify_url,
    _is_tidal_url,
    _is_youtube_url,
    _load_tracks_from_lavalink_identifier,
    _music_lazy_prefetch_tasks,
    _music_lazy_prefetch_worker,
    _other_members_in_channel,
    _play_next,
    _pop_queue_index,
    _resolve_url_tracks,
    _ResumeView,
    _schedule_music_lazy_prefetch,
    reconnect_music_voice_after_ready,
)
from bot.utils.music import (
    _is_trusted_youtube_watch_url,
    _ms,
    _music_embed,
    _music_status_embed,
    _order_youtube_search_tracks,
    _time_until_track,
    _track_label,
    _track_listen_url,
    _track_status_thumbnail_url,
    _youtube_search_track_score,
    _youtube_video_id,
)

CHANNEL_ID = 99
GUILD_ID = 1


@contextmanager
def _patch_player():
    with patch("bot.commands.music.Player", MagicMock):
        yield


def _channel(id_=CHANNEL_ID, members=None):
    ch = MagicMock(id=id_)
    ch.members = members or []
    ch.mention = f"#channel-{id_}"
    ch.connect = AsyncMock()
    ch.guild = MagicMock(id=GUILD_ID)
    return ch


def _player(channel, tracks=None, current=None, fetch_side_effect=None, play_raises=None):
    p = MagicMock(channel=channel, current=current)
    if fetch_side_effect is not None:
        p.fetch_tracks = AsyncMock(side_effect=fetch_side_effect)
    else:
        p.fetch_tracks = AsyncMock(return_value=tracks or [])
    p.play = AsyncMock(side_effect=play_raises) if play_raises else AsyncMock()
    return p


def _play_ctx(cog, tracks=None, fetch_side_effect=None, current=None, play_raises=None, queue=None):
    ch = _channel()
    p = _player(
        ch,
        tracks=tracks,
        fetch_side_effect=fetch_side_effect,
        current=current,
        play_raises=play_raises,
    )
    i = _interaction(cog.bot, voice_channel=ch)
    i.guild.voice_client = p
    if queue is not None:
        cog.bot._music_queues = {GUILD_ID: deque(queue) if not isinstance(queue, deque) else queue}
    return i, p


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.settings = SimpleNamespace(feature_music=False)
    bot.pool = MagicMock()
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.user = MagicMock(id=999)
    bot.db_pool = None
    bot.cache = None
    return bot


@pytest.fixture
def cog(mock_bot):
    return MusicCommands(mock_bot)


def _interaction(bot, guild_id=1, channel_id=2, user_id=3, voice_channel=None):
    i = MagicMock(guild_id=guild_id, channel_id=channel_id, client=bot)
    i.user = MagicMock(id=user_id)
    i.user.voice = MagicMock(channel=voice_channel) if voice_channel else None
    i.guild = MagicMock(id=guild_id, voice_client=None)
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


class TestMusicTidalResolve:
    @pytest.mark.asyncio
    async def test_resolve_tidal_catalog_lazy_tail_youtube_search(self, cog):
        p = MagicMock()
        first = MagicMock(title="First")
        with patch(
            "bot.commands.music.tidal_playlist_to_search_queries",
            AsyncMock(return_value=["A - One", "B - Two"]),
        ):
            with patch("bot.commands.music._fetch_one_track", AsyncMock(return_value=first)):
                r = await _resolve_url_tracks(
                    p, "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd", cog.bot
                )
        assert r.tracks == [first] and r.playlist
        assert r.lazy_tail is not None
        assert r.lazy_tail.search_queries == ("B - Two",)
        assert r.lazy_tail.search_type == SearchType.YOUTUBE

    @pytest.mark.asyncio
    async def test_resolve_tidal_single_query_no_lazy_tail(self, cog):
        p = MagicMock()
        only = MagicMock(title="Solo")
        with patch(
            "bot.commands.music.tidal_playlist_to_search_queries",
            AsyncMock(return_value=["Band - Only"]),
        ):
            with patch("bot.commands.music._fetch_one_track", AsyncMock(return_value=only)):
                r = await _resolve_url_tracks(
                    p, "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd", cog.bot
                )
        assert r.tracks == [only] and not r.playlist and r.lazy_tail is None

    @pytest.mark.asyncio
    async def test_resolve_tidal_first_track_unresolvable(self, cog):
        p = MagicMock()
        with patch(
            "bot.commands.music.tidal_playlist_to_search_queries",
            AsyncMock(return_value=["A - One", "B - Two"]),
        ):
            with patch("bot.commands.music._fetch_one_track", AsyncMock(return_value=None)):
                r = await _resolve_url_tracks(
                    p, "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd", cog.bot
                )
        assert r.err and "first track" in r.err.lower() and "tidal" in r.err.lower()


class TestMusicSpotifyResolve:
    @pytest.mark.asyncio
    async def test_resolve_spotify_native_returns_tracks(self, cog):
        p = MagicMock()
        tr = MagicMock()
        with patch(
            "bot.commands.music._load_tracks_from_lavalink_identifier", AsyncMock(return_value=[tr])
        ):
            r = await _resolve_url_tracks(
                p, "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq", cog.bot
            )
        assert r.tracks == [tr] and r.lazy_tail is None and r.err is None

    @pytest.mark.asyncio
    async def test_resolve_spotify_native_multi_lazy_preloads(self, cog):
        p = MagicMock()
        a, b, c = MagicMock(), MagicMock(), MagicMock()
        with patch(
            "bot.commands.music._load_tracks_from_lavalink_identifier",
            AsyncMock(return_value=[a, b, c]),
        ):
            r = await _resolve_url_tracks(
                p, "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq", cog.bot
            )
        assert r.tracks == [a] and r.playlist
        assert r.lazy_tail is not None
        assert r.lazy_tail.preloaded_tracks == (b, c)
        assert not r.lazy_tail.search_queries

    @pytest.mark.asyncio
    async def test_resolve_spotify_lazy_tail_after_first_track(self, cog):
        cog.bot.settings = SimpleNamespace(
            feature_music=True, spotify_client_id="c", spotify_client_secret="s"
        )
        p = MagicMock()
        first = MagicMock(title="First")
        with patch(
            "bot.commands.music._load_tracks_from_lavalink_identifier", AsyncMock(return_value=None)
        ):
            with patch(
                "bot.commands.music.spotify_playlist_catalog_queries",
                AsyncMock(return_value=["Artist - A", "Artist - B"]),
            ):
                with patch(
                    "bot.commands.music._fetch_one_track_spotify", AsyncMock(return_value=first)
                ):
                    r = await _resolve_url_tracks(
                        p,
                        "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq",
                        cog.bot,
                    )
        assert r.tracks == [first] and r.playlist
        assert r.lazy_tail is not None
        assert r.lazy_tail.search_queries == ("Artist - B",)
        assert r.lazy_tail.search_type == SearchType.SPOTIFY_SEARCH

    @pytest.mark.asyncio
    async def test_resolve_spotify_playlist_no_native_no_web_api_creds(self, cog):
        cog.bot.settings = SimpleNamespace(
            feature_music=True, spotify_client_id=None, spotify_client_secret=None
        )
        p = MagicMock()
        with patch(
            "bot.commands.music._load_tracks_from_lavalink_identifier", AsyncMock(return_value=None)
        ):
            r = await _resolve_url_tracks(
                p,
                "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq?si=b14fe019fa6a47fa",
                cog.bot,
            )
        assert r.err and "SPOTIFY_CLIENT_ID" in r.err and "SPOTIFY_CLIENT_SECRET" in r.err


class TestMusicLazyHelpers:
    def test_lazy_prefetch_tasks_creates_storage(self):
        bot = SimpleNamespace()
        a = _music_lazy_prefetch_tasks(cast(Any, bot))
        assert _music_lazy_prefetch_tasks(cast(Any, bot)) is a

    @pytest.mark.asyncio
    async def test_cancel_lazy_prefetch_noop_without_map(self, mock_bot):
        await _cancel_music_lazy_prefetch(mock_bot, 1)

    @pytest.mark.asyncio
    async def test_cancel_lazy_prefetch_cancels_task(self):
        bot = SimpleNamespace()
        tmap = _music_lazy_prefetch_tasks(cast(Any, bot))

        async def slow():
            await asyncio.sleep(100)

        tmap[3] = asyncio.create_task(slow())
        await _cancel_music_lazy_prefetch(cast(Any, bot), 3)
        assert 3 not in tmap

    @pytest.mark.asyncio
    async def test_cancel_lazy_prefetch_completed_task(self):
        bot = SimpleNamespace()
        tmap = _music_lazy_prefetch_tasks(cast(Any, bot))

        async def noop():
            pass

        t = asyncio.create_task(noop())
        _ = await t
        tmap[11] = t
        await _cancel_music_lazy_prefetch(cast(Any, bot), 11)

    @pytest.mark.asyncio
    async def test_lazy_prefetch_worker_cancelled_on_sleep(self, mock_bot):
        mock_bot._music_queues = {1: deque()}
        tail = MusicLazyTail(search_queries=("a",), search_type=SearchType.SPOTIFY_SEARCH)
        with patch(
            "bot.commands.music.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError())
        ):
            await _music_lazy_prefetch_worker(mock_bot, 1, MagicMock(), tail)
        assert len(_get_queue(mock_bot, 1)) == 0

    @pytest.mark.asyncio
    async def test_lazy_prefetch_worker_stops_when_queue_removed(self, mock_bot):
        mock_bot._music_queues = {}
        tail = MusicLazyTail(search_queries=("q",), search_type=SearchType.SPOTIFY_SEARCH)
        with patch("bot.commands.music.asyncio.sleep", new_callable=AsyncMock):
            await _music_lazy_prefetch_worker(mock_bot, 9, MagicMock(), tail)

    @pytest.mark.asyncio
    async def test_lazy_prefetch_worker_skips_when_resolve_returns_none(self, mock_bot):
        mock_bot._music_queues = {1: deque()}
        tail = MusicLazyTail(search_queries=("q",), search_type=SearchType.SPOTIFY_SEARCH)
        with patch("bot.commands.music.asyncio.sleep", new_callable=AsyncMock):
            with patch("bot.commands.music._fetch_one_track_spotify", AsyncMock(return_value=None)):
                await _music_lazy_prefetch_worker(mock_bot, 1, MagicMock(), tail)
        assert len(_get_queue(mock_bot, 1)) == 0

    @pytest.mark.asyncio
    async def test_lazy_prefetch_worker_appends_resolved(self, mock_bot):
        mock_bot._music_queues = {1: deque()}
        tr = MagicMock()
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=[tr])
        tail = MusicLazyTail(
            search_queries=("artist - song",), search_type=SearchType.SPOTIFY_SEARCH
        )
        with patch("bot.commands.music.asyncio.sleep", new_callable=AsyncMock):
            await _music_lazy_prefetch_worker(mock_bot, 1, p, tail)
        assert list(_get_queue(mock_bot, 1)) == [tr]

    @pytest.mark.asyncio
    async def test_lazy_prefetch_worker_appends_preloaded(self, mock_bot):
        mock_bot._music_queues = {1: deque()}
        t2 = MagicMock()
        tail = MusicLazyTail(preloaded_tracks=(t2,))
        with patch("bot.commands.music.asyncio.sleep", new_callable=AsyncMock):
            await _music_lazy_prefetch_worker(mock_bot, 1, MagicMock(), tail)
        assert list(_get_queue(mock_bot, 1)) == [t2]

    @pytest.mark.asyncio
    async def test_lazy_prefetch_worker_preloaded_then_search_queries(self, mock_bot):
        mock_bot._music_queues = {1: deque()}
        t2 = MagicMock()
        t3 = MagicMock()
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=[t3])
        tail = MusicLazyTail(
            preloaded_tracks=(t2,),
            search_queries=("q",),
            search_type=SearchType.YOUTUBE,
        )
        with patch("bot.commands.music.asyncio.sleep", new_callable=AsyncMock):
            await _music_lazy_prefetch_worker(mock_bot, 1, p, tail)
        assert list(_get_queue(mock_bot, 1)) == [t2, t3]

    def test_schedule_lazy_prefetch_empty_noop(self):
        bot = SimpleNamespace()
        _schedule_music_lazy_prefetch(cast(Any, bot), 1, MagicMock(), None)
        _schedule_music_lazy_prefetch(cast(Any, bot), 1, MagicMock(), MusicLazyTail())

    @pytest.mark.asyncio
    async def test_schedule_lazy_prefetch_replaces_previous(self):
        bot = SimpleNamespace()

        async def slow():
            await asyncio.sleep(100)

        tmap = _music_lazy_prefetch_tasks(cast(Any, bot))
        tmap[4] = asyncio.create_task(slow())
        tail = MusicLazyTail(search_queries=("only",), search_type=SearchType.SPOTIFY_SEARCH)
        _schedule_music_lazy_prefetch(cast(Any, bot), 4, MagicMock(), tail)
        assert 4 in tmap
        tmap[4].cancel()
        try:
            _ = await tmap[4]
        except asyncio.CancelledError:
            # Expected after cancel() on the replaced prefetch task.
            pass

    @pytest.mark.asyncio
    async def test_schedule_prefetch_no_previous_entry(self):
        bot = SimpleNamespace()
        bot._music_queues = {6: deque()}
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=[MagicMock()])
        tail = MusicLazyTail(search_queries=("one",), search_type=SearchType.SPOTIFY_SEARCH)
        with patch("bot.commands.music.asyncio.sleep", new_callable=AsyncMock):
            _schedule_music_lazy_prefetch(cast(Any, bot), 6, p, tail)
        t = bot._music_lazy_prefetch_tasks[6]
        _ = await t
        assert getattr(bot, "_music_lazy_prefetch_tasks", {}) == {}

    @pytest.mark.asyncio
    async def test_lazy_prefetch_worker_preload_stops_when_queue_removed_mid_loop(self, mock_bot):
        mock_bot._music_queues = {1: deque()}
        t2, t3 = MagicMock(), MagicMock()
        tail = MusicLazyTail(preloaded_tracks=(t2, t3))

        async def sleep_side_effect(_d):
            mock_bot._music_queues.pop(1, None)

        with patch("bot.commands.music.asyncio.sleep", AsyncMock(side_effect=sleep_side_effect)):
            await _music_lazy_prefetch_worker(mock_bot, 1, MagicMock(), tail)
        assert 1 not in (mock_bot._music_queues or {})

    @pytest.mark.asyncio
    async def test_load_tracks_from_lavalink_on_trackload(self):
        p = MagicMock()
        p.fetch_tracks = AsyncMock(
            side_effect=TrackLoadException(message="m", severity="common", cause="c")
        )
        assert (
            await _load_tracks_from_lavalink_identifier(p, "https://open.spotify.com/track/x")
            is None
        )

    @pytest.mark.asyncio
    async def test_load_tracks_from_lavalink_none_result(self):
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=None)
        assert await _load_tracks_from_lavalink_identifier(p, "https://x") is None

    @pytest.mark.asyncio
    async def test_load_tracks_from_lavalink_empty_list(self):
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=[])
        assert await _load_tracks_from_lavalink_identifier(p, "https://x") is None

    @pytest.mark.asyncio
    async def test_load_tracks_from_lavalink_empty_playlist(self):
        p = MagicMock()
        pl = Playlist(info={"name": "p", "selectedTrack": 0}, tracks=[], plugin_info={})
        p.fetch_tracks = AsyncMock(return_value=pl)
        assert await _load_tracks_from_lavalink_identifier(p, "https://x") is None

    @pytest.mark.asyncio
    async def test_load_tracks_from_lavalink_unknown_shape(self):
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=object())
        assert await _load_tracks_from_lavalink_identifier(p, "https://x") is None

    @pytest.mark.asyncio
    async def test_fetch_one_track_spotify_on_trackload(self):
        p = MagicMock()
        p.fetch_tracks = AsyncMock(
            side_effect=TrackLoadException(message="m", severity="common", cause="c")
        )
        assert await _fetch_one_track_spotify(p, "q") is None

    @pytest.mark.asyncio
    async def test_fetch_one_track_spotify_non_list_with_tracks(self):
        t0 = MagicMock()
        load = MagicMock(spec=["tracks"])
        load.tracks = [t0]
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=load)
        assert await _fetch_one_track_spotify(p, "q") is t0

    @pytest.mark.asyncio
    async def test_fetch_one_track_spotify_empty_list_returns_none(self):
        p = MagicMock()
        p.fetch_tracks = AsyncMock(return_value=[])
        assert await _fetch_one_track_spotify(p, "q") is None

    @pytest.mark.asyncio
    async def test_fetch_one_track_spotify_unknown_result_returns_none(self):
        p = MagicMock()
        load = MagicMock(spec=["tracks"])
        load.tracks = []
        p.fetch_tracks = AsyncMock(return_value=load)
        assert await _fetch_one_track_spotify(p, "q") is None

    @pytest.mark.asyncio
    async def test_resolve_spotify_single_catalog_entry_no_lazy_tail(self, cog):
        cog.bot.settings = SimpleNamespace(
            feature_music=True, spotify_client_id="c", spotify_client_secret="s"
        )
        p = MagicMock()
        only = MagicMock(title="Solo")
        with patch(
            "bot.commands.music._load_tracks_from_lavalink_identifier", AsyncMock(return_value=None)
        ):
            with patch(
                "bot.commands.music.spotify_playlist_catalog_queries",
                AsyncMock(return_value=["Only Artist - Only Song"]),
            ):
                with patch(
                    "bot.commands.music._fetch_one_track_spotify", AsyncMock(return_value=only)
                ):
                    r = await _resolve_url_tracks(
                        p, "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq", cog.bot
                    )
        assert r.tracks == [only] and r.lazy_tail is None and not r.playlist

    @pytest.mark.asyncio
    async def test_resolve_spotify_first_track_unresolvable(self, cog):
        cog.bot.settings = SimpleNamespace(
            feature_music=True, spotify_client_id="c", spotify_client_secret="s"
        )
        p = MagicMock()
        with patch(
            "bot.commands.music._load_tracks_from_lavalink_identifier", AsyncMock(return_value=None)
        ):
            with patch(
                "bot.commands.music.spotify_playlist_catalog_queries",
                AsyncMock(return_value=["A - B"]),
            ):
                with patch(
                    "bot.commands.music._fetch_one_track_spotify", AsyncMock(return_value=None)
                ):
                    r = await _resolve_url_tracks(
                        p, "https://open.spotify.com/playlist/7soPh0TWD5LFOt7doETqNq", cog.bot
                    )
        assert r.err and "first track" in r.err.lower()

    @pytest.mark.asyncio
    async def test_play_lazy_while_playing_schedules_prefetch_without_extra_copy(self, cog):
        t1 = MagicMock(title="QueuedFirst")
        i, player = _play_ctx(cog, tracks=[t1], current=MagicMock(title="Now"))
        tail = MusicLazyTail(search_queries=("tail-query",), search_type=SearchType.SPOTIFY_SEARCH)
        ru = ResolvedUrl([t1], True, None, None, tail)
        with patch("bot.commands.music._resolve_url_tracks", AsyncMock(return_value=ru)):
            with patch("bot.commands.music._schedule_music_lazy_prefetch", MagicMock()) as sched:
                with _patch_player():
                    await cog.music_group.play.callback(
                        cog.music_group, i, "https://open.spotify.com/playlist/x"
                    )
        desc = i.followup.send.call_args[1]["embed"].description or ""
        assert "more track" not in desc.lower() and "load into" not in desc.lower()
        sched.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_lazy_idle_schedules_prefetch_without_extra_copy(self, cog):
        t1 = MagicMock(title="Only")
        i, player = _play_ctx(cog, tracks=[t1], current=None)
        tail = MusicLazyTail(search_queries=("tail",), search_type=SearchType.SPOTIFY_SEARCH)
        ru = ResolvedUrl([t1], True, None, None, tail)
        with patch("bot.commands.music._resolve_url_tracks", AsyncMock(return_value=ru)):
            with patch("bot.commands.music._schedule_music_lazy_prefetch", MagicMock()) as sched:
                with _patch_player():
                    await cog.music_group.play.callback(
                        cog.music_group, i, "https://open.spotify.com/playlist/x"
                    )
        desc = i.followup.send.call_args[1]["embed"].description or ""
        assert "more track" not in desc.lower() and "load into" not in desc.lower()
        sched.assert_called_once()


class TestFormatDuration:
    @pytest.mark.parametrize(
        "ms,expected",
        [
            (0, "live"),
            (-1, "live"),
            (65000, "1:05"),
            (185000, "3:05"),
            (3665000, "1:01:05"),
        ],
    )
    def test_format(self, ms, expected):
        assert _format_duration(ms) == expected


class TestMusicUtils:
    def test_ms_none_returns_zero(self):
        assert _ms(None) == 0

    def test_ms_invalid_returns_zero(self):
        assert _ms("x") == 0
        assert _ms(object()) == 0

    def test_ms_valid_returns_int(self):
        assert _ms(5000) == 5000
        assert _ms("5000") == 5000

    def test_music_embed(self):
        emb = _music_embed("Title", "Desc")
        assert emb.title == "Title"
        assert emb.description == "Desc"

    def test_track_label_with_author(self):
        t = MagicMock(title="Song", author="Artist")
        assert "Artist" in _track_label(t, 1) and "Song" in _track_label(t, 1)

    def test_track_label_no_author(self):
        t = MagicMock(title="Song", spec=["title"])
        assert _track_label(t, 1).startswith("1.")

    def test_yt_score_prefers_official_over_reaction(self):
        low = MagicMock(title="Song REACTION", author="Channel", length=180_000)
        high = MagicMock(title="Song (Official Video)", author="Artist", length=180_000)
        assert _youtube_search_track_score(high) > _youtube_search_track_score(low)

    def test_yt_score_vevo(self):
        t = MagicMock(title="Song", author="ArtistVEVO", length=180_000)
        assert _youtube_search_track_score(t) >= 28

    def test_yt_score_long_over_short_clip(self):
        long = MagicMock(title="Live Performance", author="Band", length=200_000)
        clip = MagicMock(title="Live Performance", author="Band", length=20_000)
        assert _youtube_search_track_score(long) > _youtube_search_track_score(clip)

    def test_yt_score_clamps_negative(self):
        t = MagicMock(
            title=" reaction  cover  karaoke  nightcore  mashup ",
            author=" x ",
            length=20_000,
        )
        assert _youtube_search_track_score(t) == -80

    def test_yt_order_official_first(self):
        a = MagicMock(title="Track REACTION", author="X", length=200_000)
        b = MagicMock(title="Track (Official Video)", author="Y", length=200_000)
        ordered = _order_youtube_search_tracks([a, b])
        assert ordered[0] is b and ordered[1] is a

    def test_yt_order_single_unchanged(self):
        t = MagicMock(title="Only", author="A", length=100_000)
        assert _order_youtube_search_tracks([t]) == [t]

    def test_time_until_track_idx_zero_no_current(self):
        assert _time_until_track(None, None, [], 0) == "—"

    def test_time_until_track_idx_zero_with_current(self):
        player = MagicMock(position=5000)
        current = MagicMock(length=65000)
        assert "left" in _time_until_track(player, current, [], 0)

    def test_time_until_track_idx_nonzero(self):
        q = [MagicMock(length=60000)]
        assert "in " in _time_until_track(None, None, q, 1)

    def test_time_until_track_idx_two_sums_queue(self):
        q = [MagicMock(length=60000), MagicMock(length=120000)]
        result = _time_until_track(None, None, q, 2)
        assert "in " in result


class TestYoutubeVideoId:
    def test_from_watch_url(self):
        assert _youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "") == "dQw4w9WgXcQ"

    def test_from_youtu_be(self):
        assert _youtube_video_id("https://youtu.be/dQw4w9WgXcQ", "") == "dQw4w9WgXcQ"

    def test_from_embed_path(self):
        assert _youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ", "") == "dQw4w9WgXcQ"

    def test_from_shorts_path(self):
        assert _youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ", "") == "dQw4w9WgXcQ"

    def test_from_m_youtube_host(self):
        assert _youtube_video_id("https://m.youtube.com/watch?v=jNQXAC9IVRw", "") == "jNQXAC9IVRw"

    def test_watch_path_without_v_query_falls_back_to_identifier(self):
        assert _youtube_video_id("https://www.youtube.com/watch", "jNQXAC9IVRw") == "jNQXAC9IVRw"

    def test_from_identifier_only(self):
        assert _youtube_video_id(None, "dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_identifier_wrong_length(self):
        assert _youtube_video_id(None, "tooshort") is None

    def test_uri_without_hostname_falls_back_to_identifier(self):
        assert _youtube_video_id("http:///watch?v=jNQXAC9IVRw", "jNQXAC9IVRw") == "jNQXAC9IVRw"

    def test_youtu_be_empty_segment_falls_back(self):
        assert _youtube_video_id("https://youtu.be/", "dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_urlparse_error_falls_back_to_identifier(self):
        with patch("bot.utils.music.urlparse", side_effect=ValueError("bad")):
            assert (
                _youtube_video_id("https://www.youtube.com/watch?v=xx", "dQw4w9WgXcQ")
                == "dQw4w9WgXcQ"
            )


class TestTrackListenAndArt:
    def test_listen_prefers_http_uri(self):
        t = MagicMock(uri="https://example.com/track", identifier="", source="http")
        assert _track_listen_url(t) == "https://example.com/track"

    def test_listen_youtube_from_source_and_identifier(self):
        t = MagicMock(uri=None, identifier="dQw4w9WgXcQ", source="youtube")
        assert _track_listen_url(t) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_thumbnail_prefers_artwork(self):
        t = MagicMock(
            artwork_url="https://cdn.example/cover.jpg",
            uri=None,
            identifier="",
        )
        assert _track_status_thumbnail_url(t) == "https://cdn.example/cover.jpg"

    def test_thumbnail_youtube_fallback(self):
        t = MagicMock(
            artwork_url=None,
            uri="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            identifier="",
        )
        assert _track_status_thumbnail_url(t) == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"

    def test_thumbnail_none_without_art_or_youtube(self):
        t = MagicMock(
            artwork_url=None,
            uri="https://example.com/audio",
            identifier="",
        )
        assert _track_status_thumbnail_url(t) is None

    def test_listen_returns_non_http_uri_when_no_youtube_match(self):
        t = MagicMock(uri="spotify:track:abc", identifier="", source="spotify")
        assert _track_listen_url(t) == "spotify:track:abc"

    def test_listen_returns_ftp_uri(self):
        t = MagicMock(uri="ftp://example.com/a", identifier="", source="ftp")
        assert _track_listen_url(t) == "ftp://example.com/a"

    def test_listen_youtube_source_without_resolvable_id(self):
        t = MagicMock(uri=None, identifier="", source="youtube")
        assert _track_listen_url(t) is None


class TestMusicStatusEmbed:
    def test_idle_no_current_track(self):
        p = MagicMock(current=None, position=0, paused=False)
        emb = _music_status_embed(p, "#music-vc", paused=False)
        assert "Music status" in emb.title and "Nothing playing" in emb.description

    def test_idle_paused_shows_pause_note(self):
        p = MagicMock(current=None, position=0, paused=True)
        emb = _music_status_embed(p, "#music-vc", paused=True)
        assert "Paused" in emb.description and "Nothing playing" in emb.description

    def test_playing_shows_timing_and_youtube_link(self):
        cur = MagicMock(
            title="Song",
            author="Artist",
            length=180_000,
            uri="https://www.youtube.com/watch?v=jNQXAC9IVRw",
            identifier="",
            artwork_url=None,
            stream=False,
        )
        p = MagicMock(current=cur, position=30_000, paused=False)
        emb = _music_status_embed(p, "#vc", paused=False)
        assert "Now playing" in emb.title
        assert "Open on YouTube" in emb.description
        assert "Time left" in emb.description and "Total length" in emb.description
        assert "Elapsed" in emb.description
        assert emb.thumbnail
        thumb = urlparse(emb.thumbnail.url)
        assert thumb.scheme == "https" and thumb.hostname == "i.ytimg.com"
        assert thumb.path.startswith("/vi/jNQXAC9IVRw/")

    def test_stream_shows_position_not_countdown(self):
        cur = MagicMock(
            title="Live",
            author="Host",
            length=9_000_000_000_000,
            uri="https://example.com/live",
            identifier="",
            stream=True,
        )
        p = MagicMock(current=cur, position=5_000, paused=False)
        emb = _music_status_embed(p, "#vc", paused=False)
        assert "live stream" in emb.description.lower()
        assert "Position:" in emb.description

    def test_paused_note_when_playing(self):
        cur = MagicMock(
            title="X",
            author="Y",
            length=60_000,
            uri="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            stream=False,
            identifier="",
        )
        emb = _music_status_embed(
            MagicMock(current=cur, position=1_000, paused=True), "#c", paused=True
        )
        assert "Paused" in emb.description

    def test_open_track_link_for_non_youtube(self):
        cur = MagicMock(
            title="T",
            author="A",
            length=30_000,
            uri="https://soundcloud.com/u/song",
            stream=False,
            identifier="",
            artwork_url=None,
        )
        emb = _music_status_embed(
            MagicMock(current=cur, position=5_000, paused=False), "#c", paused=False
        )
        assert "Open track" in emb.description and "Open on YouTube" not in emb.description

    def test_no_listen_url_skips_link_lines(self):
        cur = MagicMock(
            title="Orphan",
            author="",
            length=25_000,
            uri=None,
            stream=False,
            identifier="",
            artwork_url=None,
        )
        emb = _music_status_embed(
            MagicMock(current=cur, position=0, paused=False), "#c", paused=False
        )
        assert "Open on YouTube" not in emb.description and "Open track" not in emb.description
        assert emb.thumbnail.url is None

    def test_long_track_length_stream_style_timing(self):
        cur = MagicMock(
            title="X",
            author="",
            length=10**15,
            uri="https://example.com/x",
            stream=False,
            identifier="",
            artwork_url=None,
        )
        emb = _music_status_embed(
            MagicMock(current=cur, position=1, paused=False), "#c", paused=False
        )
        assert "live stream" in emb.description.lower()

    def test_deceptive_listen_url_uses_open_track_not_youtube_label(self):
        cur = MagicMock(
            title="T",
            author="A",
            length=30_000,
            uri="https://evil.example/path/youtube.com/watch?v=jNQXAC9IVRw",
            stream=False,
            identifier="",
            artwork_url=None,
        )
        emb = _music_status_embed(
            MagicMock(current=cur, position=0, paused=False), "#c", paused=False
        )
        assert "Open track" in emb.description and "Open on YouTube" not in emb.description


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=jNQXAC9IVRw", True),
        ("https://youtu.be/jNQXAC9IVRw", True),
        ("https://m.youtube.com/watch?v=jNQXAC9IVRw", True),
        ("https://music.youtube.com/watch?v=jNQXAC9IVRw", True),
        ("https://gaming.youtube.com/watch?v=jNQXAC9IVRw", True),
        ("https://www.youtube.com/embed/jNQXAC9IVRw", True),
        ("https://www.youtube.com/shorts/jNQXAC9IVRw", True),
        ("http://www.youtube.com/watch?v=jNQXAC9IVRw", False),
        ("https://evil.example/youtube.com", False),
        ("https://www.youtube.com/watch?v=short", False),
        ("https://www.youtube.com/watch?", False),
        ("https://youtu.be/", False),
        ("https://youtu.be/bad/id", False),
        ("https://www.youtube.com/channel/UCabcdefghijk", False),
        (1, False),
    ],
)
def test_is_trusted_youtube_watch_url(url, expected):
    assert _is_trusted_youtube_watch_url(url) is expected


class TestQueueHelpers:
    def test_get_queue_creates_defaultdict(self, mock_bot):
        if hasattr(mock_bot, "_music_queues"):
            del mock_bot._music_queues
        q = _get_queue(mock_bot, 123)
        assert q == deque() and 123 in mock_bot._music_queues

    def test_clear_queue(self, mock_bot):
        mock_bot._music_queues = {1: deque([MagicMock()])}
        _clear_queue(mock_bot, 1)
        assert 1 not in mock_bot._music_queues

    def test_clear_queue_not_present_no_op(self, mock_bot):
        mock_bot._music_queues = {1: deque()}
        _clear_queue(mock_bot, 2)
        assert 1 in mock_bot._music_queues

    @pytest.mark.parametrize(
        "idx,expected_title,remaining",
        [
            (0, "A", ["B", "C"]),
            (1, "B", ["A", "C"]),
            (2, "C", ["A", "B"]),
        ],
    )
    def test_pop_queue_index_preserves_order(self, idx, expected_title, remaining):
        queue = deque(MagicMock(title=t) for t in ("A", "B", "C"))
        popped = _pop_queue_index(queue, idx)
        assert popped.title == expected_title
        assert [t.title for t in queue] == remaining


class TestPlayNext:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "queue,expected,called",
        [
            ([], False, False),
            ([MagicMock()], True, True),
        ],
    )
    async def test_play_next(self, mock_bot, queue, expected, called):
        track = queue[0] if queue else None
        player = MagicMock(guild=MagicMock(id=GUILD_ID), client=mock_bot)
        mock_bot._music_queues = {GUILD_ID: deque(queue)}
        player.play = AsyncMock()
        result = await _play_next(player)
        assert result is expected
        if called:
            player.play.assert_called_once_with(track)
            assert mock_bot._music_queues[GUILD_ID] == deque()
        else:
            player.play.assert_not_called()


class TestPlaylistTrackFetch:
    @pytest.mark.asyncio
    async def test_fetch_playlist_tracks_preserves_query_order(self):
        player = MagicMock()
        query_delays = {"q1": 0.03, "q2": 0.0, "q3": 0.01}

        async def fake_fetch_one_track(_player, query):
            await asyncio.sleep(query_delays[query])
            return MagicMock(title=f"{query}-title")

        with patch("bot.commands.music._fetch_one_track", side_effect=fake_fetch_one_track):
            tracks = await _fetch_playlist_tracks(player, ["q1", "q2", "q3"])

        assert [t.title for t in tracks] == ["q1-title", "q2-title", "q3-title"]

    @pytest.mark.asyncio
    async def test_fetch_playlist_tracks_filters_missing_results(self):
        player = MagicMock()

        async def fake_fetch_one_track(_player, query):
            if query == "missing":
                return None
            return MagicMock(title=query)

        with patch("bot.commands.music._fetch_one_track", side_effect=fake_fetch_one_track):
            tracks = await _fetch_playlist_tracks(player, ["first", "missing", "third"])

        assert [t.title for t in tracks] == ["first", "third"]

    @pytest.mark.asyncio
    async def test_fetch_playlist_tracks_propagates_fetch_errors(self):
        player = MagicMock()

        async def fake_fetch_one_track(_player, query):
            if query == "boom":
                raise RuntimeError("fetch failed")
            return MagicMock(title=query)

        with patch("bot.commands.music._fetch_one_track", side_effect=fake_fetch_one_track):
            with pytest.raises(RuntimeError, match="fetch failed"):
                await _fetch_playlist_tracks(player, ["ok", "boom", "later"])

    @pytest.mark.asyncio
    async def test_fetch_playlist_tracks_respects_concurrency_limit(self):
        player = MagicMock()
        active = 0
        max_active = 0
        lock = asyncio.Lock()
        queries = [f"q{i}" for i in range(PLAYLIST_FETCH_CONCURRENCY + 3)]

        async def fake_fetch_one_track(_player, query):
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1
            return MagicMock(title=query)

        with patch("bot.commands.music._fetch_one_track", side_effect=fake_fetch_one_track):
            tracks = await _fetch_playlist_tracks(player, queries)

        assert len(tracks) == len(queries)
        assert max_active <= PLAYLIST_FETCH_CONCURRENCY


class TestMusicJoin:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "setup,substr",
        [
            ("no_voice", "voice channel"),
            ("disabled", "not enabled"),
            ("timeout", "timed out"),
            ("success", "Joined"),
            ("different_channel", "currently in"),
        ],
    )
    async def test_join(self, cog, setup, substr):
        if setup == "no_voice":
            i = _interaction(cog.bot)
            i.user.voice = None
        elif setup == "disabled":
            cog.bot.pool = None
            i = _interaction(cog.bot, voice_channel=_channel())
        elif setup == "timeout":
            ch = _channel()
            ch.connect = AsyncMock(side_effect=TimeoutError)
            i = _interaction(cog.bot, voice_channel=ch)
            i.guild.voice_client = None
        elif setup == "success":
            ch = _channel()
            ch.mention = "#general"
            i = _interaction(cog.bot, voice_channel=ch)
            i.guild.voice_client = None
        else:
            user_ch = _channel()
            user_ch.mention = "#user-voice"
            vc = MagicMock()
            vc.channel = MagicMock(id=888)
            i = _interaction(cog.bot, voice_channel=user_ch)
            i.guild.voice_client = vc
        await cog.music_group.join.callback(cog.music_group, i)
        kw = i.followup.send.call_args[1]
        c = (i.followup.send.call_args[0][0] or "") if i.followup.send.call_args[0] else ""
        emb = kw.get("embed") or MagicMock(title="", description="")
        assert substr.lower() in (c + emb.title + (emb.description or "")).lower()
        if setup in ("timeout", "different_channel"):
            assert kw["ephemeral"] is True
        if setup == "success":
            assert "general" in kw["embed"].description
        if setup == "different_channel":
            i.guild.voice_client.disconnect.assert_not_called()


class TestMusicPlay:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "setup,query,substr,ephemeral",
        [
            ("empty", "   ", "URL or search", False),
            ("no_voice", "never gonna give you up", "voice channel", False),
            ("disabled", "test query", "not enabled", False),
            ("timeout", "never gonna give you up", "timed out", True),
        ],
    )
    async def test_play_early_exit(self, cog, setup, query, substr, ephemeral):
        if setup == "empty":
            i = _interaction(cog.bot, voice_channel=_channel())
        elif setup == "no_voice":
            i = _interaction(cog.bot)
            i.user.voice = None
        elif setup == "disabled":
            cog.bot.pool = None
            i = _interaction(cog.bot, voice_channel=_channel())
        else:
            ch = _channel()
            ch.connect = AsyncMock(side_effect=TimeoutError)
            i = _interaction(cog.bot, voice_channel=ch)
            i.guild.voice_client = None
        await cog.music_group.play.callback(cog.music_group, i, query)
        i.followup.send.assert_called_once()
        c = (i.followup.send.call_args[0][0] or "") if i.followup.send.call_args[0] else ""
        assert substr.lower() in c.lower() and (
            not ephemeral or i.followup.send.call_args[1]["ephemeral"]
        )

    @pytest.mark.asyncio
    async def test_play_player_not_connected(self, cog):
        i, _ = _play_ctx(cog, tracks=[MagicMock()], play_raises=PlayerNotConnected)
        with _patch_player():
            await cog.music_group.play.callback(cog.music_group, i, "never gonna give you up")
        assert "music connection failed" in i.followup.send.call_args[0][0].lower()
        assert i.followup.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resolver,url,search_query,tracks",
        [
            (
                "tidal_url_to_search_query",
                "https://tidal.com/track/110653480/u",
                "Excision & Dion Timmer - Time Stood Still",
                [MagicMock(title="Excision (Official Audio)")],
            ),
            (
                "spotify_url_to_search_query",
                "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh",
                "Michael Jackson - Billie Jean",
                [MagicMock(title="Billie Jean (Official Video)")],
            ),
        ],
    )
    async def test_play_url_resolved_to_youtube(self, cog, resolver, url, search_query, tracks):
        i, player = _play_ctx(cog, tracks=tracks)
        spotify_native = (
            patch(
                "bot.commands.music._load_tracks_from_lavalink_identifier",
                AsyncMock(return_value=None),
            )
            if resolver.startswith("spotify")
            else nullcontext()
        )
        with spotify_native:
            with patch(f"bot.commands.music.{resolver}", AsyncMock(return_value=search_query)):
                with _patch_player():
                    await cog.music_group.play.callback(cog.music_group, i, url)
        expected = (
            SearchType.SPOTIFY_SEARCH if resolver.startswith("spotify") else SearchType.YOUTUBE
        )
        player.fetch_tracks.assert_called_once_with(search_query, search_type=expected)
        assert "Playing" in i.followup.send.call_args[1]["embed"].title

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resolver,url,queries",
        [
            (
                "tidal_playlist_to_search_queries",
                "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd",
                ["Dance Gavin Dance - Blood Wolf", "Delta Heavy - Reborn"],
            ),
            (
                "spotify_playlist_catalog_queries",
                "https://open.spotify.com/playlist/5bCeKZhm0Vrk4cOydmil2N",
                ["Yuka Kitamura - Slave Knight Gael", "Yuka Kitamura - Soul of Cinder"],
            ),
            (
                "tidal_album_to_search_queries",
                "https://tidal.com/album/476908869/u",
                ["Good Kid - Track A", "Good Kid - Track B"],
            ),
            (
                "spotify_album_catalog_queries",
                "https://open.spotify.com/album/1abcdefghijklmnop",
                ["Band - Alpha", "Band - Beta"],
            ),
        ],
    )
    async def test_play_playlist_queues_tracks(self, cog, resolver, url, queries):
        t1, t2 = MagicMock(title="A"), MagicMock(title="B")
        i, player = _play_ctx(cog, fetch_side_effect=[[t1], [t2]])
        spotify_native = (
            patch(
                "bot.commands.music._load_tracks_from_lavalink_identifier",
                AsyncMock(return_value=None),
            )
            if resolver.startswith("spotify")
            else nullcontext()
        )
        with (
            spotify_native,
            patch("bot.commands.music._schedule_music_lazy_prefetch", MagicMock()),
            patch(f"bot.commands.music.{resolver}", AsyncMock(return_value=queries)),
            _patch_player(),
        ):
            await cog.music_group.play.callback(cog.music_group, i, url)
        assert player.fetch_tracks.call_count == 1
        d = (i.followup.send.call_args[1]["embed"].description or "").lower()
        assert "playlist" in d or "queued" in d

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resolver,url,msg",
        [
            (
                "tidal_url_to_search_query",
                "https://tidal.com/track/110653480/u",
                "Could not resolve Tidal",
            ),
            (
                "spotify_url_to_search_query",
                "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh",
                "Could not resolve Spotify",
            ),
        ],
    )
    async def test_play_url_unresolvable(self, cog, resolver, url, msg):
        i, _ = _play_ctx(cog)
        with _patch_player():
            with patch(f"bot.commands.music.{resolver}", AsyncMock(return_value=None)):
                await cog.music_group.play.callback(cog.music_group, i, url)
        assert msg in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_play_spotify_url_multiple_hits_shows_picker(self, cog):
        t_react = MagicMock(title="Slave Knight Gael REACTION", author="Fan")
        t_official = MagicMock(title="Slave Knight Gael (Official Video)", author="From")
        i, player = _play_ctx(cog, tracks=[t_react, t_official])
        with patch(
            "bot.commands.music.spotify_url_to_search_query",
            AsyncMock(return_value="Yuka Kitamura - Slave Knight Gael"),
        ):
            with patch(
                "bot.commands.music._load_tracks_from_lavalink_identifier",
                AsyncMock(return_value=None),
            ):
                with _patch_player():
                    await cog.music_group.play.callback(
                        cog.music_group, i, "https://open.spotify.com/track/74m8PoL6GZulfVzeYS6W0C"
                    )
        player.play.assert_not_called()
        kw = i.followup.send.call_args[1]
        assert "Pick a track" in kw["embed"].title and kw.get("view") and kw["ephemeral"]
        assert len(_get_queue(cog.bot, GUILD_ID)) == 0

    @pytest.mark.asyncio
    async def test_play_tidal_track_url_multiple_hits_shows_picker(self, cog):
        t_lyrics = MagicMock(title="Unanswered (Lyrics)", author="Ch")
        t_official = MagicMock(title="Unanswered (OFFICIAL VIDEO)", author="SS")
        i, player = _play_ctx(cog, tracks=[t_lyrics, t_official])
        with patch(
            "bot.commands.music.tidal_url_to_search_query",
            AsyncMock(return_value="Suicide Silence - Unanswered"),
        ):
            with _patch_player():
                await cog.music_group.play.callback(
                    cog.music_group, i, "https://tidal.com/track/51982148/u"
                )
        player.play.assert_not_called()
        kw = i.followup.send.call_args[1]
        assert "Pick a track" in kw["embed"].title and kw.get("view")
        assert len(_get_queue(cog.bot, GUILD_ID)) == 0

    @pytest.mark.asyncio
    async def test_play_spotify_track_url_while_playing_multiple_hits_shows_picker(self, cog):
        t_react = MagicMock(title="Unanswered REACTION", author="X")
        t_official = MagicMock(title="Unanswered (Official Video)", author="Y")
        i, player = _play_ctx(
            cog, tracks=[t_react, t_official], current=MagicMock(title="Now Playing"), queue=[]
        )
        with patch(
            "bot.commands.music.spotify_url_to_search_query",
            AsyncMock(return_value="Suicide Silence - Unanswered"),
        ):
            with patch(
                "bot.commands.music._load_tracks_from_lavalink_identifier",
                AsyncMock(return_value=None),
            ):
                with _patch_player():
                    await cog.music_group.play.callback(
                        cog.music_group, i, "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
                    )
        assert len(_get_queue(cog.bot, GUILD_ID)) == 0
        kw = i.followup.send.call_args[1]
        assert "Pick a track" in kw["embed"].title and kw.get("view")

    @pytest.mark.asyncio
    async def test_play_force_next_mod_inserts_at_front(self, cog):
        track = MagicMock(title="Force Play Song")
        i, player = _play_ctx(
            cog,
            tracks=[track],
            current=MagicMock(title="Now Playing"),
            queue=[MagicMock(title="Existing")],
        )
        with _patch_player():
            await cog.music_group.play.callback(cog.music_group, i, "search query", force_next=True)
        assert cog.bot._music_queues[GUILD_ID][0].title == "Force Play Song"
        assert "playing next" in (i.followup.send.call_args[1]["embed"].description or "").lower()

    @pytest.mark.asyncio
    async def test_play_force_next_non_mod_denied(self, cog):
        cog.bot.permission_checker.check_role = AsyncMock(return_value=False)
        i, _ = _play_ctx(cog, tracks=[MagicMock(title="Song")])
        with _patch_player():
            await cog.music_group.play.callback(cog.music_group, i, "search query", force_next=True)
        assert "Moderator" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_play_queued_while_paused_includes_resume_button(self, cog):
        i, player = _play_ctx(
            cog,
            tracks=[MagicMock(title="Queued Song")],
            current=MagicMock(title="Now Playing"),
            queue=[],
        )
        player.paused = True
        with _patch_player():
            await cog.music_group.play.callback(cog.music_group, i, "another song")
        kw = i.followup.send.call_args[1]
        assert kw.get("view") and kw.get("embed") and "Queued" in kw["embed"].title

    @pytest.mark.asyncio
    async def test_play_multiple_results_shows_ephemeral_picker(self, cog):
        t1, t2 = MagicMock(title="Song A", author="Artist 1"), MagicMock(
            title="Song B", author="Artist 2"
        )
        i, _ = _play_ctx(cog, tracks=[t1, t2])
        with _patch_player():
            await cog.music_group.play.callback(cog.music_group, i, "search query")
        kw = i.followup.send.call_args[1]
        assert "Pick a track" in kw["embed"].title and kw.get("view") and kw["ephemeral"]

    @pytest.mark.asyncio
    async def test_track_picker_choice_enqueues_when_playing(self, cog):
        t0, t1 = MagicMock(title="Pick A", author="A1"), MagicMock(title="Pick B", author="A2")
        ch = _channel()
        p = _player(ch, current=MagicMock(title="Current"))
        p.guild = MagicMock(id=GUILD_ID)
        if hasattr(cog.bot, "_music_queues"):
            del cog.bot._music_queues
        view = TrackPickerView([t0, t1], p, cog.bot)
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        i.response.send_message = AsyncMock()
        await view.children[0].callback(i)
        p.play.assert_not_called()
        assert list(_get_queue(cog.bot, GUILD_ID)) == [t0]
        emb = i.response.edit_message.call_args[1]["embed"]
        assert "Queued" in emb.title and "Pick A" in (emb.description or "")

    @pytest.mark.asyncio
    async def test_track_picker_choice_when_paused_includes_resume_view(self, cog):
        t0 = MagicMock(title="Pick A", author="A1")
        ch = _channel()
        p = _player(ch, current=MagicMock(title="Current"))
        p.guild = MagicMock(id=GUILD_ID)
        p.paused = True
        if hasattr(cog.bot, "_music_queues"):
            del cog.bot._music_queues
        view = TrackPickerView([t0, MagicMock(title="B", author="A2")], p, cog.bot)
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view.children[0].callback(i)
        assert i.response.edit_message.call_args[1]["view"] is not None

    @pytest.mark.asyncio
    async def test_track_picker_choice_plays_when_idle(self, cog):
        t0 = MagicMock(title="Pick A", author="Artist")
        ch = _channel()
        p = _player(ch, current=None)
        p.guild = MagicMock(id=GUILD_ID)
        view = TrackPickerView([t0], p, cog.bot)
        i = MagicMock()
        i.response.edit_message = AsyncMock()
        await view.children[0].callback(i)
        p.play.assert_called_once_with(t0)
        assert "Playing" in i.response.edit_message.call_args[1]["embed"].title

    @pytest.mark.asyncio
    async def test_play_search_non_list_load_shows_picker_not_full_queue(self, cog):
        t1, t2, t3 = (
            MagicMock(title="Hit A", author="X"),
            MagicMock(title="Hit B", author="Y"),
            MagicMock(title="Hit C", author="Z"),
        )
        load = MagicMock(tracks=[t1, t2, t3])
        ch = _channel()
        p = _player(ch, tracks=None)
        p.fetch_tracks = AsyncMock(return_value=load)
        i = _interaction(cog.bot, voice_channel=ch)
        i.guild.voice_client = p
        with _patch_player():
            await cog.music_group.play.callback(cog.music_group, i, "architects everything ends")
        p.fetch_tracks.assert_called_once()
        call_kw = p.fetch_tracks.call_args[1]
        assert call_kw.get("search_type") is SearchType.YOUTUBE
        kw = i.followup.send.call_args[1]
        assert "Pick a track" in kw["embed"].title and kw.get("view")
        assert len(_get_queue(cog.bot, GUILD_ID)) == 0

    @pytest.mark.asyncio
    async def test_play_youtube_url_playlist_shape_queues_all(self, cog):
        t1, t2 = MagicMock(title="PL A"), MagicMock(title="PL B")
        load = MagicMock(tracks=[t1, t2])
        ch = _channel()
        p = _player(ch, tracks=None, current=MagicMock(title="Now"))
        p.fetch_tracks = AsyncMock(return_value=load)
        i = _interaction(cog.bot, voice_channel=ch)
        i.guild.voice_client = p
        cog.bot._music_queues = {GUILD_ID: deque()}
        with (
            _patch_player(),
            patch("bot.commands.music._schedule_music_lazy_prefetch", MagicMock()) as sch,
        ):
            await cog.music_group.play.callback(
                cog.music_group, i, "https://www.youtube.com/playlist?list=PLtest"
            )
        p.fetch_tracks.assert_called_once()
        assert p.fetch_tracks.call_args[1].get("search_type") is None
        assert list(cog.bot._music_queues[GUILD_ID]) == [t1]
        tail = sch.call_args[0][3]
        assert tail.preloaded_tracks == (t2,)
        desc = (i.followup.send.call_args[1]["embed"].description or "").lower()
        assert "added" in desc and "more track" not in desc and "load into" not in desc

    @pytest.mark.asyncio
    async def test_play_youtube_playlist_prefix_size(self, cog):
        many = [MagicMock(title=f"T{n}") for n in range(60)]
        load = MagicMock(tracks=many)
        ch = _channel()
        p = _player(ch, tracks=None, current=MagicMock(title="Now"))
        p.fetch_tracks = AsyncMock(return_value=load)
        i = _interaction(cog.bot, voice_channel=ch)
        i.guild.voice_client = p
        cog.bot._music_queues = {GUILD_ID: deque()}
        with (
            _patch_player(),
            patch("bot.commands.music._schedule_music_lazy_prefetch", MagicMock()) as sch,
        ):
            await cog.music_group.play.callback(
                cog.music_group, i, "https://www.youtube.com/playlist?list=PLbig"
            )
        q = list(cog.bot._music_queues[GUILD_ID])
        assert len(q) == 1 and q[0] is many[0]
        tail = sch.call_args[0][3]
        assert len(tail.preloaded_tracks) == YOUTUBE_PLAYLIST_RESOLVE_SAMPLE - 1
        assert tail.preloaded_tracks[0] is many[1]

    @pytest.mark.asyncio
    async def test_play_youtube_playlist_catalog_cap_before_prefix(self, cog):
        over_cap = [MagicMock(title=f"T{n}") for n in range(YOUTUBE_PLAYLIST_CATALOG_MAX + 5)]
        load = MagicMock(tracks=over_cap)
        ch = _channel()
        p = _player(ch, tracks=None, current=MagicMock(title="Now"))
        p.fetch_tracks = AsyncMock(return_value=load)
        i = _interaction(cog.bot, voice_channel=ch)
        i.guild.voice_client = p
        cog.bot._music_queues = {GUILD_ID: deque()}
        with (
            _patch_player(),
            patch("bot.commands.music._schedule_music_lazy_prefetch", MagicMock()) as sch,
        ):
            await cog.music_group.play.callback(
                cog.music_group, i, "https://www.youtube.com/playlist?list=PLcap"
            )
        tail = sch.call_args[0][3]
        assert len(tail.preloaded_tracks) == YOUTUBE_PLAYLIST_RESOLVE_SAMPLE - 1
        assert tail.preloaded_tracks[0] is over_cap[1]

    @pytest.mark.asyncio
    async def test_play_idle_two_pre_resolved_tracks_queues_second(self, cog):
        t0, t1 = MagicMock(title="A"), MagicMock(title="B")
        ch = _channel()
        p = _player(ch, tracks=[t0], current=None)
        i = _interaction(cog.bot, voice_channel=ch)
        i.guild.voice_client = p
        cog.bot._music_queues = {GUILD_ID: deque()}
        ru = ResolvedUrl([t0, t1], True, None, None, None)
        with patch("bot.commands.music._resolve_url_tracks", AsyncMock(return_value=ru)):
            with _patch_player():
                await cog.music_group.play.callback(
                    cog.music_group, i, "https://open.spotify.com/playlist/abc"
                )
        assert list(cog.bot._music_queues[GUILD_ID]) == [t1]

    @pytest.mark.asyncio
    async def test_status_music_disabled(self, cog):
        cog.bot.pool = None
        i = _interaction(cog.bot, voice_channel=_channel())
        await cog.music_group.status.callback(cog.music_group, i)
        assert "not enabled" in i.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_status_not_in_voice(self, cog):
        i = _interaction(cog.bot)
        i.guild.voice_client = None
        cog.bot.voice_clients = []
        await cog.music_group.status.callback(cog.music_group, i)
        d = (i.followup.send.call_args[1]["embed"].description or "").lower()
        assert "not connected" in d

    @pytest.mark.asyncio
    async def test_status_connected_idle(self, cog):
        ch = _channel()
        p = MagicMock(channel=ch, current=None, paused=False)
        i = _interaction(cog.bot)
        i.guild.voice_client = p
        cog.bot.voice_clients = []
        with _patch_player():
            await cog.music_group.status.callback(cog.music_group, i)
        emb = i.followup.send.call_args[1]["embed"]
        assert "Nothing playing" in emb.description and ch.mention in emb.description

    @pytest.mark.asyncio
    async def test_status_now_playing(self, cog):
        cur = MagicMock(
            title="Song",
            author="Artist",
            length=120_000,
            uri="https://www.youtube.com/watch?v=jNQXAC9IVRw",
            identifier="",
            stream=False,
        )
        ch = _channel()
        p = MagicMock(channel=ch, current=cur, position=10_000, paused=False)
        i = _interaction(cog.bot)
        i.guild.voice_client = p
        cog.bot.voice_clients = []
        with _patch_player():
            await cog.music_group.status.callback(cog.music_group, i)
        emb = i.followup.send.call_args[1]["embed"]
        assert "Now playing" in emb.title and "Time left" in emb.description


class TestMusicLeave:
    @pytest.mark.asyncio
    async def test_leave_not_connected(self, cog):
        i = _interaction(cog.bot)
        i.guild.voice_client = None
        cog.bot.voice_clients = []
        await cog.music_group.leave.callback(cog.music_group, i)
        assert "Not in" in i.followup.send.call_args[0][0]


class TestMusicAdmin:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "queue_len,substr",
        [
            (2, "2"),
            (0, "already empty"),
        ],
    )
    async def test_clear_queue(self, cog, queue_len, substr):
        cog.bot._music_queues = {GUILD_ID: deque([MagicMock()] * queue_len)}
        i = _interaction(cog.bot)
        await cog.music_group.clear_queue.callback(cog.music_group, i)
        if queue_len:
            assert GUILD_ID not in cog.bot._music_queues
            assert "Cleared" in i.followup.send.call_args[1]["embed"].title
        assert substr in i.followup.send.call_args[1]["embed"].description

    @pytest.mark.asyncio
    async def test_force_play_position(self, cog):
        t1, t2 = MagicMock(title="Next"), MagicMock(title="Forced")
        i, player = _play_ctx(cog, current=MagicMock(title="Now Playing"), queue=[t1, t2])
        player.stop = AsyncMock()
        with _patch_player():
            await cog.music_group.force_play.callback(cog.music_group, i, 2)
        player.play.assert_called_once_with(t2)
        assert cog.bot._music_queues[GUILD_ID][0].title == "Now Playing"
        assert "Force Playing" in i.followup.send.call_args[1]["embed"].title


class TestMusicQueue:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "has_player,check",
        [
            (False, lambda kw: "empty" in (kw["embed"].description or "").lower()),
            (True, lambda kw: "Music Queue" in kw["embed"].title and kw.get("view")),
        ],
    )
    async def test_queue(self, cog, has_player, check):
        i = _interaction(cog.bot)
        cog.bot._music_queues = {GUILD_ID: deque()}
        i.guild.voice_client = (
            MagicMock(current=MagicMock(title="Test Song", uri="x", length=180000), position=0)
            if has_player
            else None
        )
        with _patch_player():
            await cog.music_group.queue_cmd.callback(cog.music_group, i)
        assert check(i.followup.send.call_args[1])


class TestOtherMembersInChannel:
    @pytest.mark.parametrize(
        "members,bot_id,expected",
        [
            ([MagicMock(id=1), MagicMock(id=2)], 1, 1),
            ([], 99, 0),
        ],
    )
    def test_excludes_bot(self, members, bot_id, expected):
        ch = MagicMock(members=members)
        assert _other_members_in_channel(ch, bot_id) == expected


class TestVoiceStateUpdate:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("pool_none,user_none", [(True, False), (False, True)])
    async def test_skips_when_no_pool_or_user(self, cog, pool_none, user_none):
        cog.bot.pool = None if pool_none else MagicMock()
        cog.bot.user = None if user_none else MagicMock()
        await cog._on_voice_state_update(MagicMock(), MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_cancels_task_when_someone_joins(self, cog):
        cog.bot.pool = MagicMock()
        cog.bot.user = MagicMock(id=999)
        channel = _channel(id_=1, members=[MagicMock(id=1), MagicMock(id=999)])
        vc = MagicMock(channel=channel, guild=channel.guild)
        cog.bot.voice_clients = [vc]
        task = asyncio.create_task(asyncio.sleep(60))
        cog.bot._music_leave_tasks = {GUILD_ID: task}
        await cog._on_voice_state_update(
            MagicMock(), MagicMock(channel=None), MagicMock(channel=channel)
        )
        assert GUILD_ID not in cog.bot._music_leave_tasks


class TestMusicCogUnload:
    @pytest.mark.asyncio
    async def test_cog_unload_removes_command(self, cog):
        cog.bot.tree.remove_command = MagicMock()
        await cog.cog_unload()
        cog.bot.tree.remove_command.assert_called_once_with("music")


class TestMusicVoiceRecovery:
    @pytest.mark.asyncio
    async def test_reconnect_skips_without_pool(self, mock_bot):
        mock_bot.settings.feature_music = True
        mock_bot.pool = None
        mock_bot.db_pool = MagicMock()
        with patch("bot.commands.music.fetch_music_voice_channel_targets", AsyncMock()) as f:
            await reconnect_music_voice_after_ready(mock_bot)
        f.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconnect_skips_without_db_pool(self, mock_bot):
        mock_bot.settings.feature_music = True
        mock_bot.pool = MagicMock()
        mock_bot.db_pool = None
        with patch("bot.commands.music.fetch_music_voice_channel_targets", AsyncMock()) as f:
            await reconnect_music_voice_after_ready(mock_bot)
        f.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconnect_skips_when_feature_off(self, mock_bot):
        mock_bot.settings.feature_music = False
        mock_bot.pool = MagicMock()
        mock_bot.db_pool = MagicMock()
        with patch("bot.commands.music.fetch_music_voice_channel_targets", AsyncMock()) as f:
            await reconnect_music_voice_after_ready(mock_bot)
        f.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconnect_calls_connect(self, mock_bot):
        mock_bot.settings.feature_music = True
        mock_bot.pool = MagicMock()
        mock_bot.db_pool = MagicMock()
        ch = MagicMock()
        ch.id = 88
        ch.connect = AsyncMock()
        guild = MagicMock(id=1, voice_client=None)
        guild.get_channel = MagicMock(return_value=ch)
        guild.me = MagicMock()
        ch.permissions_for = MagicMock(return_value=MagicMock(connect=True, speak=True))
        mock_bot.guilds = [guild]
        with patch(
            "bot.commands.music.fetch_music_voice_channel_targets",
            AsyncMock(return_value=[(1, 88)]),
        ):
            with patch("bot.commands.music._is_voice_or_stage", return_value=True):
                with _patch_player():
                    await reconnect_music_voice_after_ready(mock_bot)
        ch.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconnect_clears_when_not_voice_channel(self, mock_bot):
        mock_bot.settings.feature_music = True
        mock_bot.pool = MagicMock()
        mock_bot.db_pool = MagicMock()
        guild = MagicMock(id=1, voice_client=None)
        guild.get_channel = MagicMock(return_value=MagicMock())
        mock_bot.guilds = [guild]
        with patch(
            "bot.commands.music.fetch_music_voice_channel_targets",
            AsyncMock(return_value=[(1, 88)]),
        ):
            with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as s:
                await reconnect_music_voice_after_ready(mock_bot)
        s.assert_awaited_once_with(mock_bot.db_pool, 1, None, None)

    @pytest.mark.asyncio
    async def test_voice_state_persists_channel(self, cog):
        cog.bot.settings.feature_music = True
        cog.bot.db_pool = MagicMock()
        cog.bot.pool = None
        bot_uid = cog.bot.user.id
        ch = MagicMock()
        member = MagicMock(id=bot_uid, guild=MagicMock(id=GUILD_ID))
        before = MagicMock(channel=None)
        after = MagicMock(channel=ch)
        with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as m:
            with patch("bot.commands.music._is_voice_or_stage", return_value=True):
                await cog._on_voice_state_update(member, before, after)
        m.assert_awaited_once_with(cog.bot.db_pool, member.guild.id, ch.id, cog.bot.cache)


class TestMusicTrackEndListener:
    def test_cog_registers_on_track_end(self):
        assert ("on_track_end", "_on_track_end") in MusicCommands.__cog_listeners__

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "reason, expect_play_next",
        [
            (EndReason.FINISHED, True),
            (EndReason.LOAD_FAILED, True),
            (EndReason.STOPPED, False),
        ],
    )
    async def test_on_track_end(self, cog, reason, expect_play_next):
        player = MagicMock(guild=MagicMock(id=GUILD_ID), client=cog.bot)
        event = MagicMock(reason=reason, player=player)
        with patch("bot.commands.music._play_next", new_callable=AsyncMock) as m:
            await cog._on_track_end(event)
        if expect_play_next:
            m.assert_awaited_once_with(player)
        else:
            m.assert_not_called()


class TestMusicUrlHelpers:
    def test_get_url_host_invalid_parse_returns_empty(self):
        with patch("bot.commands.music.urlparse", side_effect=TypeError("bad")):
            assert _get_url_host("https://example.com/x") == ""

    def test_is_tidal_spotify_youtube_hosts(self):
        assert _is_tidal_url("https://listen.tidal.com/track/1")
        assert _is_spotify_url("https://open.spotify.com/track/x")
        assert _is_youtube_url("https://www.youtube.com/watch?v=x")


@pytest.mark.asyncio
async def test_play_next_player_not_connected_returns_false(mock_bot):
    t = MagicMock()
    player = MagicMock(guild=MagicMock(id=GUILD_ID), client=mock_bot)
    mock_bot._music_queues = {GUILD_ID: deque([t])}
    player.play = AsyncMock(side_effect=PlayerNotConnected)
    assert await _play_next(player) is False
    assert mock_bot._music_queues[GUILD_ID][0] is t


@pytest.mark.asyncio
async def test_fetch_one_track_non_list_result(mock_bot):
    player = MagicMock()
    load = MagicMock(tracks=[MagicMock(title="a")])
    player.fetch_tracks = AsyncMock(return_value=load)
    out = await _fetch_one_track(player, "q")
    assert out is load.tracks[0]


@pytest.mark.asyncio
async def test_resume_view_button_when_not_paused():
    player = MagicMock(paused=False)
    view = _ResumeView(player)
    i = MagicMock()
    i.response.edit_message = AsyncMock()
    i.response.defer = AsyncMock()
    btn = view.children[0]
    await btn.callback(i)
    i.response.defer.assert_awaited()


@pytest.mark.asyncio
async def test_track_picker_double_fire_defers(cog):
    t = MagicMock(title="X", author="Y")
    ch = _channel()
    p = _player(ch, current=MagicMock(title="C"))
    p.guild = MagicMock(id=GUILD_ID)
    view = TrackPickerView([t], p, cog.bot)
    i = MagicMock()
    i.response.edit_message = AsyncMock()
    i.response.defer = AsyncMock()
    await view.children[0].callback(i)
    await view.children[0].callback(i)
    assert i.response.defer.await_count >= 1


@pytest.mark.asyncio
async def test_track_picker_play_raises_not_connected(cog):
    t = MagicMock(title="X", author="Y")
    ch = _channel()
    p = _player(ch, current=None, play_raises=PlayerNotConnected)
    p.guild = MagicMock(id=GUILD_ID)
    view = TrackPickerView([t], p, cog.bot)
    i = MagicMock()
    i.response.edit_message = AsyncMock()
    i.response.send_message = AsyncMock()
    await view.children[0].callback(i)
    assert CONNECTION_FAILED_MSG in i.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_leave_clears_stale_db_when_no_vc(cog):
    cog.bot.db_pool = MagicMock()
    i = _interaction(cog.bot)
    i.guild.voice_client = None
    cog.bot.voice_clients = []
    with patch(
        "bot.commands.music.get_music_voice_channel_id",
        AsyncMock(return_value=555),
    ):
        with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as s:
            await cog.music_group.leave.callback(cog.music_group, i)
    s.assert_awaited()


@pytest.mark.asyncio
async def test_skip_when_queue_empty_after_skip(cog):
    with _patch_player():
        i, player = _play_ctx(cog, current=MagicMock(title="X"), queue=[])
        player.stop = AsyncMock()
        with patch("bot.commands.music._play_next", AsyncMock(return_value=False)):
            await cog.music_group.skip.callback(cog.music_group, i)
    args, kw = i.followup.send.call_args
    emb = kw.get("embed")
    parts = [str(a) for a in args]
    if emb:
        parts.extend([emb.title or "", emb.description or ""])
    assert "Skipped" in " ".join(parts)


@pytest.mark.asyncio
async def test_force_play_bad_position_and_not_connected(cog):
    with _patch_player():
        i, player = _play_ctx(cog, current=MagicMock(title="N"), queue=[MagicMock(title="A")])
        await cog.music_group.force_play.callback(cog.music_group, i, 99)
    assert "No track at position" in i.followup.send.call_args[0][0]

    t = MagicMock(title="T")
    with _patch_player():
        i2, p2 = _play_ctx(cog, current=MagicMock(title="N"), queue=[t])
        p2.play = AsyncMock(side_effect=PlayerNotConnected)
        p2.stop = AsyncMock()
        await cog.music_group.force_play.callback(cog.music_group, i2, 1)
    assert CONNECTION_FAILED_MSG in i2.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_cancel_leave_task_swallows_cancelled():
    tasks = {}
    t = asyncio.create_task(asyncio.sleep(60))
    tasks[1] = t
    await _cancel_leave_task(tasks, 1)
    assert 1 not in tasks


@pytest.mark.asyncio
async def test_voice_idle_schedules_leave(cog):
    cog.bot.settings.feature_music = True
    cog.bot.pool = MagicMock()
    cog.bot.user = MagicMock(id=999)
    cog.bot.db_pool = None
    channel = _channel(id_=5, members=[MagicMock(id=999)])
    vc = MagicMock(channel=channel, guild=channel.guild)
    cog.bot.voice_clients = [vc]
    before = MagicMock(channel=channel)
    after = MagicMock(channel=None)
    member = MagicMock(id=7)

    def _fake_create_task(coro):
        coro.close()
        return MagicMock(cancel=MagicMock())

    with patch("asyncio.create_task", side_effect=_fake_create_task) as ct:
        await cog._on_voice_state_update(member, before, after)
    ct.assert_called_once()


@pytest.mark.asyncio
async def test_reconnect_skips_when_guild_unknown(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    mock_bot.guilds = []
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[(999, 1)]),
    ):
        await reconnect_music_voice_after_ready(mock_bot)


@pytest.mark.asyncio
async def test_reconnect_disconnect_failure_logged(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    vc = MagicMock()
    vc.channel = MagicMock(id=2)
    vc.disconnect = AsyncMock(side_effect=RuntimeError("dc"))
    guild = MagicMock(id=1, voice_client=vc)
    guild.get_channel = MagicMock(return_value=_channel(id_=88))
    guild.me = MagicMock()
    mock_bot.guilds = [guild]
    ch = guild.get_channel.return_value
    ch.permissions_for = MagicMock(return_value=MagicMock(connect=True, speak=True))
    ch.connect = AsyncMock()
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[(1, 88)]),
    ):
        with patch("bot.commands.music._is_voice_or_stage", return_value=True):
            with _patch_player():
                await reconnect_music_voice_after_ready(mock_bot)


@pytest.mark.asyncio
async def test_reconnect_skips_when_already_connected_same_channel(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    ch = _channel(id_=88)
    vc = MagicMock(channel=ch)
    guild = MagicMock(id=1, voice_client=vc)
    guild.get_channel = MagicMock(return_value=ch)
    mock_bot.guilds = [guild]
    ch.connect = AsyncMock()
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[(1, 88)]),
    ):
        await reconnect_music_voice_after_ready(mock_bot)
    ch.connect.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_empty_targets(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[]),
    ):
        await reconnect_music_voice_after_ready(mock_bot)


@pytest.mark.asyncio
async def test_reconnect_skips_when_guild_me_none(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    ch = _channel(id_=88)
    guild = MagicMock(id=1, voice_client=None)
    guild.get_channel = MagicMock(return_value=ch)
    guild.me = None
    mock_bot.guilds = [guild]
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[(1, 88)]),
    ):
        with patch("bot.commands.music._is_voice_or_stage", return_value=True):
            await reconnect_music_voice_after_ready(mock_bot)


@pytest.mark.asyncio
async def test_reconnect_clears_binding_when_channel_not_voice(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    guild = MagicMock(id=1, voice_client=None)
    guild.get_channel = MagicMock(return_value=MagicMock())
    guild.me = MagicMock()
    mock_bot.guilds = [guild]
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[(1, 55)]),
    ):
        with patch("bot.commands.music._is_voice_or_stage", return_value=False):
            with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as sm:
                await reconnect_music_voice_after_ready(mock_bot)
    sm.assert_awaited()


@pytest.mark.asyncio
async def test_reconnect_connect_failure_clears_binding(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    ch = _channel(id_=88)
    ch.connect = AsyncMock(side_effect=RuntimeError("fail"))
    ch.permissions_for = MagicMock(return_value=MagicMock(connect=True, speak=True))
    guild = MagicMock(id=1, voice_client=None)
    guild.get_channel = MagicMock(return_value=ch)
    guild.me = MagicMock()
    mock_bot.guilds = [guild]
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[(1, 88)]),
    ):
        with patch("bot.commands.music._is_voice_or_stage", return_value=True):
            with _patch_player():
                with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as sm:
                    await reconnect_music_voice_after_ready(mock_bot)
    sm.assert_awaited()


@pytest.mark.asyncio
async def test_reconnect_missing_voice_permissions(mock_bot):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    ch = _channel(id_=88)
    ch.permissions_for = MagicMock(return_value=MagicMock(connect=False, speak=True))
    guild = MagicMock(id=1, voice_client=None)
    guild.get_channel = MagicMock(return_value=ch)
    guild.me = MagicMock()
    mock_bot.guilds = [guild]
    with patch(
        "bot.commands.music.fetch_music_voice_channel_targets",
        AsyncMock(return_value=[(1, 88)]),
    ):
        with patch("bot.commands.music._is_voice_or_stage", return_value=True):
            with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as sm:
                with _patch_player():
                    await reconnect_music_voice_after_ready(mock_bot)
    sm.assert_awaited()


def test_get_url_host_non_http_query():
    assert _get_url_host("search text") == ""


@pytest.mark.asyncio
async def test_fetch_one_track_returns_none_for_empty():
    player = MagicMock()
    player.fetch_tracks = AsyncMock(return_value=[])
    assert await _fetch_one_track(player, "q") is None


@pytest.mark.asyncio
async def test_fetch_one_track_returns_none_when_load_has_no_tracks():
    player = MagicMock()
    load = MagicMock(tracks=[])
    player.fetch_tracks = AsyncMock(return_value=load)
    assert await _fetch_one_track(player, "q") is None


@pytest.mark.asyncio
async def test_resume_view_when_paused_calls_resume():
    player = MagicMock(paused=True)
    player.resume = AsyncMock()
    view = _ResumeView(player)
    i = MagicMock()
    i.response.edit_message = AsyncMock()
    btn = view.children[0]
    await btn.callback(i)
    player.resume.assert_awaited()
    i.response.edit_message.assert_awaited()


@pytest.mark.asyncio
async def test_check_voice_pool_returns_none_without_guild(mock_bot, cog):
    mock_bot.pool = MagicMock()
    ch = _channel()
    i = _interaction(mock_bot, voice_channel=ch)
    i.guild = None
    i.followup.send = AsyncMock()
    assert await _check_voice_pool(i) is None


@pytest.mark.asyncio
async def test_ensure_player_wrong_voice_channel(mock_bot, cog):
    mock_bot.pool = MagicMock()
    ch = _channel(id_=100)
    vc = MagicMock()
    vc.channel = MagicMock(id=99)
    i = _interaction(mock_bot, voice_channel=ch)
    i.guild.voice_client = vc
    i.followup.send = AsyncMock()
    with _patch_player():
        assert await _ensure_player(i) is None


@pytest.mark.asyncio
async def test_join_bot_already_in_user_channel(mock_bot, cog):
    mock_bot.pool = MagicMock()
    ch = _channel()
    vc = MagicMock(channel=ch)
    i = _interaction(mock_bot, voice_channel=ch)
    i.guild.voice_client = vc
    i.followup.send = AsyncMock()
    await cog.music_group.join.callback(cog.music_group, i)
    assert "Already" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_play_fetch_returns_none(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    i, p = _play_ctx(cog, fetch_side_effect=None)
    p.fetch_tracks = AsyncMock(return_value=None)
    p.current = MagicMock(title="Now")
    with patch("bot.commands.music._is_allowed_music_url", return_value=False):
        await cog.music_group.play.callback(cog.music_group, i, "q", False)
    assert "No results" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_play_no_tracks_after_fetch(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    i, p = _play_ctx(cog, fetch_side_effect=None)
    p.fetch_tracks = AsyncMock(return_value=[])
    p.current = MagicMock(title="Now")
    with patch("bot.commands.music._is_allowed_music_url", return_value=False):
        await cog.music_group.play.callback(cog.music_group, i, "search", False)
    assert "No tracks" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_play_force_next_denied_for_non_mod(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.permission_checker.check_role = AsyncMock(return_value=False)
    t = MagicMock(title="A")
    i, p = _play_ctx(cog, tracks=[t, MagicMock(title="B")])
    p.current = MagicMock(title="Now")
    with patch("bot.commands.music._is_allowed_music_url", return_value=False):
        await cog.music_group.play.callback(cog.music_group, i, "x", True)
    assert "Moderator" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_play_queue_when_paused_includes_resume_view(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    t = MagicMock(title="Queued")
    i, p = _play_ctx(cog, tracks=[t])
    p.current = MagicMock(title="Now")
    p.paused = True
    with patch("bot.commands.music._is_allowed_music_url", return_value=False):
        await cog.music_group.play.callback(cog.music_group, i, "findme", False)
    assert i.followup.send.call_args[1].get("view") is not None


@pytest.mark.asyncio
async def test_leave_not_in_voice_no_stale_record(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = None
    i = _interaction(mock_bot)
    i.guild.voice_client = None
    cog.bot.voice_clients = []
    await cog.music_group.leave.callback(cog.music_group, i)
    assert "Not in a voice" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_leave_disconnects_when_connected(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    ch = _channel()
    vc = MagicMock(channel=ch, disconnect=AsyncMock())
    i = _interaction(mock_bot)
    i.guild.voice_client = vc
    cog.bot.voice_clients = [vc]
    with patch("bot.commands.music._get_voice_client", return_value=vc):
        with patch("bot.commands.music._cancel_leave_task", new_callable=AsyncMock):
            await cog.music_group.leave.callback(cog.music_group, i)
    vc.disconnect.assert_awaited()


@pytest.mark.asyncio
async def test_pause_when_already_paused(mock_bot, cog):
    mock_bot.pool = MagicMock()
    p = MagicMock()
    p.paused = True
    p.current = MagicMock(title="T")
    i = _interaction(mock_bot)
    i.guild.voice_client = p
    with _patch_player():
        await cog.music_group.pause.callback(cog.music_group, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "Already paused" in (emb.title or "")


@pytest.mark.asyncio
async def test_resume_when_not_paused(mock_bot, cog):
    mock_bot.pool = MagicMock()
    p = MagicMock()
    p.paused = False
    p.current = MagicMock(title="T")
    i = _interaction(mock_bot)
    i.guild.voice_client = p
    with _patch_player():
        await cog.music_group.resume.callback(cog.music_group, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "Not paused" in (emb.title or "")


@pytest.mark.asyncio
async def test_status_no_pool(mock_bot, cog):
    mock_bot.pool = None
    i = _interaction(mock_bot)
    await cog.music_group.status.callback(cog.music_group, i)
    assert "not enabled" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_status_no_guild(mock_bot, cog):
    mock_bot.pool = MagicMock()
    i = _interaction(mock_bot)
    i.guild = None
    await cog.music_group.status.callback(cog.music_group, i)


@pytest.mark.asyncio
async def test_skip_plays_next_track(mock_bot, cog):
    mock_bot.pool = MagicMock()
    nxt = MagicMock(title="Next")
    i, p = _play_ctx(cog, current=MagicMock(title="Cur"), queue=[nxt])
    p.stop = AsyncMock()
    with _patch_player():
        with patch("bot.commands.music._play_next", new=AsyncMock(return_value=True)):
            await cog.music_group.skip.callback(cog.music_group, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "Now playing" in ((emb.title or "") + (emb.description or ""))


@pytest.mark.asyncio
async def test_clear_queue_requires_admin(mock_bot, cog):
    mock_bot.pool = MagicMock()
    with patch("bot.commands.music.require_admin", AsyncMock(return_value=False)):
        i = _interaction(mock_bot)
        await cog.music_group.clear_queue.callback(cog.music_group, i)


@pytest.mark.asyncio
async def test_clear_queue_empty(mock_bot, cog):
    mock_bot.pool = MagicMock()
    with patch("bot.commands.music.require_admin", AsyncMock(return_value=True)):
        i = _interaction(mock_bot)
        cog.bot._music_queues = {GUILD_ID: deque()}
        with _patch_player():
            await cog.music_group.clear_queue.callback(cog.music_group, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "empty" in (emb.description or "").lower()


@pytest.mark.asyncio
async def test_force_play_position_zero(mock_bot, cog):
    mock_bot.pool = MagicMock()
    with patch("bot.commands.music.require_admin", AsyncMock(return_value=True)):
        with _patch_player():
            i, _ = _play_ctx(cog, queue=[MagicMock(title="A")])
            await cog.music_group.force_play.callback(cog.music_group, i, 0)
    assert "at least 1" in i.followup.send.call_args[0][0].lower()


def test_get_leave_tasks_initializes_storage():
    from types import SimpleNamespace

    bot = SimpleNamespace()
    r = _get_leave_tasks(bot)
    assert r is _get_leave_tasks(bot) and isinstance(r, dict)


@pytest.mark.asyncio
async def test_voice_state_bot_disconnect_clears_binding(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.db_pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    member = MagicMock(id=999, guild=MagicMock(id=GUILD_ID))
    before = MagicMock(channel=MagicMock())
    after = MagicMock(channel=None)
    with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as sm:
        await cog._on_voice_state_update(member, before, after)
    sm.assert_awaited_with(mock_bot.db_pool, GUILD_ID, None, mock_bot.cache)


@pytest.mark.asyncio
async def test_voice_state_skips_vc_without_channel(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    vc = MagicMock(channel=None, guild=MagicMock(id=GUILD_ID))
    cog.bot.voice_clients = [vc]
    member = MagicMock(id=8)
    before = MagicMock(channel=None)
    after = MagicMock(channel=MagicMock(id=1))
    await cog._on_voice_state_update(member, before, after)


@pytest.mark.asyncio
async def test_voice_state_cancels_leave_when_others_join(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    ch = _channel(id_=5, members=[MagicMock(id=1), MagicMock(id=999)])
    vc = MagicMock(channel=ch, guild=ch.guild)
    cog.bot.voice_clients = [vc]
    member = MagicMock(id=8)
    before = MagicMock(channel=None)
    after = MagicMock(channel=ch)
    with patch("bot.commands.music._cancel_leave_task", new_callable=AsyncMock) as cc:
        await cog._on_voice_state_update(member, before, after)
    cc.assert_awaited()


@pytest.mark.asyncio
async def test_on_track_end_logs_when_queue_advances(mock_bot, cog):
    player = MagicMock(guild=MagicMock(id=GUILD_ID), client=cog.bot)
    event = MagicMock(reason=EndReason.FINISHED, player=player)
    with patch("bot.commands.music._play_next", new=AsyncMock(return_value=True)):
        with patch("bot.commands.music.logger") as log:
            await cog._on_track_end(event)
    log.debug.assert_called()


@pytest.mark.asyncio
async def test_play_youtube_url_non_list_sets_playlist_flag(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    load = MagicMock()
    load.tracks = [MagicMock(title=f"T{n}") for n in range(3)]
    i, p = _play_ctx(cog, fetch_side_effect=None)
    p.fetch_tracks = AsyncMock(return_value=load)
    p.current = MagicMock(title="Now")
    with patch("bot.commands.music._is_allowed_music_url", return_value=True):
        with patch("bot.commands.music._is_youtube_url", return_value=True):
            with patch("bot.commands.music._resolve_url_tracks", new_callable=AsyncMock) as rv:
                rv.return_value = ResolvedUrl(None, False, None, None)
                await cog.music_group.play.callback(
                    cog.music_group,
                    i,
                    "https://www.youtube.com/watch?v=abc",
                    False,
                )
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_play_queue_not_paused_no_resume_view(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    t = MagicMock(title="One")
    i, p = _play_ctx(cog, tracks=[t])
    p.current = MagicMock(title="Cur")
    p.paused = False
    with patch("bot.commands.music._is_allowed_music_url", return_value=False):
        await cog.music_group.play.callback(cog.music_group, i, "find", False)
    assert i.followup.send.call_args[1].get("view") is None


@pytest.mark.asyncio
async def test_leave_no_voice_stale_not_configured(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.db_pool = MagicMock()
    i = _interaction(mock_bot)
    i.guild.voice_client = None
    cog.bot.voice_clients = []
    with patch("bot.commands.music.get_music_voice_channel_id", AsyncMock(return_value=None)):
        await cog.music_group.leave.callback(cog.music_group, i)
    assert "Not in a voice" in i.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_queue_cmd_voice_client_not_player(mock_bot, cog):
    mock_bot.pool = MagicMock()
    i = _interaction(mock_bot)
    i.guild.voice_client = MagicMock()
    await cog.music_group.queue_cmd.callback(cog.music_group, i)
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_status_not_connected(mock_bot, cog):
    mock_bot.pool = MagicMock()
    i = _interaction(mock_bot)
    i.guild.voice_client = MagicMock()
    await cog.music_group.status.callback(cog.music_group, i)
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_skip_next_title_when_no_current(mock_bot, cog):
    mock_bot.pool = MagicMock()
    i, p = _play_ctx(cog, current=None, queue=[MagicMock(title="N")])
    p.stop = AsyncMock()
    with _patch_player():
        with patch("bot.commands.music._play_next", new=AsyncMock(return_value=True)):
            await cog.music_group.skip.callback(cog.music_group, i)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert emb.description


@pytest.mark.asyncio
async def test_force_play_requires_admin(mock_bot, cog):
    mock_bot.pool = MagicMock()
    with patch("bot.commands.music.require_admin", AsyncMock(return_value=False)):
        with _patch_player():
            i, _ = _play_ctx(cog, queue=[MagicMock(title="A")])
            await cog.music_group.force_play.callback(cog.music_group, i, 1)


@pytest.mark.asyncio
async def test_force_play_replaces_current(mock_bot, cog):
    mock_bot.pool = MagicMock()
    with patch("bot.commands.music.require_admin", AsyncMock(return_value=True)):
        with _patch_player():
            cur = MagicMock(title="Cur")
            nxt = MagicMock(title="Next")
            i, p = _play_ctx(cog, current=cur, queue=[nxt])
            p.stop = AsyncMock()
            await cog.music_group.force_play.callback(cog.music_group, i, 1)
    p.stop.assert_awaited()


@pytest.mark.asyncio
async def test_bot_joins_voice_updates_binding(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.db_pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    ch = _channel()
    member = MagicMock(id=999, guild=MagicMock(id=GUILD_ID))
    before = MagicMock(channel=None)
    after = MagicMock(channel=ch)
    with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as sm:
        with patch("bot.commands.music._is_voice_or_stage", return_value=True):
            await cog._on_voice_state_update(member, before, after)
    sm.assert_awaited()


@pytest.mark.asyncio
async def test_bot_leaves_voice_clears_music_channel_binding(mock_bot, cog):
    from bot.commands import music as music_mod

    mock_bot.settings.feature_music = True
    mock_bot.db_pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    ch = _channel()
    member = MagicMock(id=999, guild=MagicMock(id=GUILD_ID))
    before = MagicMock(channel=ch)
    after = MagicMock(channel=None)
    with patch.object(music_mod, "set_music_voice_channel", new_callable=AsyncMock) as sm:
        await cog._on_voice_state_update(member, before, after)
    sm.assert_awaited_once_with(mock_bot.db_pool, GUILD_ID, None, mock_bot.cache)


@pytest.mark.asyncio
async def test_bot_voice_both_channels_none_skips_music_binding(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.db_pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    member = MagicMock(id=999, guild=MagicMock(id=GUILD_ID))
    before = MagicMock(channel=None)
    after = MagicMock(channel=None)
    with patch("bot.commands.music.set_music_voice_channel", new_callable=AsyncMock) as sm:
        await cog._on_voice_state_update(member, before, after)
    sm.assert_not_called()


@pytest.mark.asyncio
async def test_track_end_finished_without_next(mock_bot, cog):
    player = MagicMock(guild=MagicMock(id=GUILD_ID), client=cog.bot)
    event = MagicMock(reason=EndReason.FINISHED, player=player)
    with patch("bot.commands.music._play_next", new=AsyncMock(return_value=False)):
        await cog._on_track_end(event)


@pytest.mark.asyncio
async def test_music_setup_loads_cog(mock_bot):
    from bot.commands import music as music_mod

    mock_bot.add_cog = AsyncMock()
    await music_mod.setup(mock_bot)
    mock_bot.add_cog.assert_awaited_once()


class _MusicPlayerType:
    pass


@pytest.mark.asyncio
async def test_play_non_youtube_non_list_multi_track_marks_playlist(mock_bot, cog):
    mock_bot.pool = MagicMock()
    mock_bot.permission_checker.check_role = AsyncMock(return_value=True)
    load = MagicMock()
    load.tracks = [MagicMock(title=f"T{n}") for n in range(3)]
    i, p = _play_ctx(cog, fetch_side_effect=None)
    p.fetch_tracks = AsyncMock(return_value=load)
    p.current = MagicMock(title="Now")
    with patch("bot.commands.music._is_allowed_music_url", return_value=True):
        with patch("bot.commands.music._is_youtube_url", return_value=False):
            with patch("bot.commands.music._resolve_url_tracks", new_callable=AsyncMock) as rv:
                rv.return_value = ResolvedUrl(None, False, None, None)
                await cog.music_group.play.callback(
                    cog.music_group,
                    i,
                    "https://open.spotify.com/track/abc",
                    False,
                )
    assert i.followup.send.await_args


@pytest.mark.asyncio
async def test_pause_when_voice_client_not_player_sends_nothing_playing(mock_bot, cog):
    mock_bot.pool = MagicMock()
    i = _interaction(mock_bot)
    i.guild.voice_client = MagicMock()
    with patch("bot.commands.music.Player", _MusicPlayerType):
        await cog.music_group.pause.callback(cog.music_group, i)
    assert "nothing playing" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_pause_executes_pause_and_followup(mock_bot, cog):
    mock_bot.pool = MagicMock()
    p = _MusicPlayerType()
    p.paused = False
    p.current = MagicMock(title="Track")
    p.pause = AsyncMock()
    i = _interaction(mock_bot)
    i.guild.voice_client = p
    with patch("bot.commands.music.Player", _MusicPlayerType):
        await cog.music_group.pause.callback(cog.music_group, i)
    p.pause.assert_awaited()


@pytest.mark.asyncio
async def test_resume_executes_resume_and_followup(mock_bot, cog):
    mock_bot.pool = MagicMock()
    p = _MusicPlayerType()
    p.paused = True
    p.current = MagicMock(title="Track")
    p.resume = AsyncMock()
    i = _interaction(mock_bot)
    i.guild.voice_client = p
    with patch("bot.commands.music.Player", _MusicPlayerType):
        await cog.music_group.resume.callback(cog.music_group, i)
    p.resume.assert_awaited()


@pytest.mark.asyncio
async def test_skip_when_voice_client_wrong_type(mock_bot, cog):
    mock_bot.pool = MagicMock()
    i = _interaction(mock_bot)
    i.guild.voice_client = object()
    with patch("bot.commands.music.Player", _MusicPlayerType):
        await cog.music_group.skip.callback(cog.music_group, i)
    assert "nothing playing" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_force_play_when_voice_client_wrong_type(mock_bot, cog):
    mock_bot.pool = MagicMock()
    with patch("bot.commands.music.require_admin", AsyncMock(return_value=True)):
        i = _interaction(mock_bot)
        i.guild.voice_client = object()
        with patch("bot.commands.music.Player", _MusicPlayerType):
            await cog.music_group.force_play.callback(cog.music_group, i, 1)
    assert "voice channel" in i.followup.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_force_play_without_current_plays_queue_track(mock_bot, cog):
    mock_bot.pool = MagicMock()
    with patch("bot.commands.music.require_admin", AsyncMock(return_value=True)):
        with _patch_player():
            nxt = MagicMock(title="Next")
            i, p = _play_ctx(cog, current=None, queue=[nxt])
            await cog.music_group.force_play.callback(cog.music_group, i, 1)
    p.play.assert_awaited_with(nxt)
    p.stop.assert_not_called()


@pytest.mark.asyncio
async def test_voice_state_unrelated_channel_move_no_idle_task(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    cog.bot._music_leave_tasks = {}
    bot_ch = _channel(id_=5)
    vc = MagicMock(channel=bot_ch, guild=bot_ch.guild)
    cog.bot.voice_clients = [vc]
    ch7 = MagicMock(id=7)
    ch8 = MagicMock(id=8)
    member = MagicMock(id=22)
    before = MagicMock(channel=ch7)
    after = MagicMock(channel=ch8)
    await cog._on_voice_state_update(member, before, after)
    assert GUILD_ID not in cog.bot._music_leave_tasks


@pytest.mark.asyncio
async def test_idle_leave_skips_disconnect_when_vc_gone_after_sleep(mock_bot, cog):
    from bot.commands import music as music_mod

    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    cog.bot._music_leave_tasks = {}
    ch = _channel(id_=5, members=[MagicMock(id=999)])
    vc = MagicMock(channel=ch, guild=ch.guild, disconnect=AsyncMock())
    cog.bot.voice_clients = [vc]
    before = MagicMock(channel=ch)
    after = MagicMock(channel=None)
    member = MagicMock(id=7)

    with patch.object(music_mod.asyncio, "sleep", new_callable=AsyncMock):
        with patch("bot.commands.music.IDLE_LEAVE_SECONDS", 0):
            with patch("bot.commands.music._get_voice_client", return_value=None):
                with patch("bot.commands.music._other_members_in_channel", return_value=0):
                    with patch("bot.commands.music._clear_queue") as cq:
                        with patch("bot.commands.music.logger"):
                            await cog._on_voice_state_update(member, before, after)
                            task = cog.bot._music_leave_tasks[GUILD_ID]
                            _ = await task
    vc.disconnect.assert_not_awaited()
    cq.assert_not_called()
    assert GUILD_ID not in cog.bot._music_leave_tasks


@pytest.mark.asyncio
async def test_idle_leave_skips_disconnect_when_others_joined(mock_bot, cog):
    from bot.commands import music as music_mod

    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    cog.bot._music_leave_tasks = {}
    ch = _channel(id_=5, members=[MagicMock(id=999)])
    vc = MagicMock(channel=ch, guild=ch.guild, disconnect=AsyncMock())
    cog.bot.voice_clients = [vc]
    before = MagicMock(channel=ch)
    after = MagicMock(channel=None)
    member = MagicMock(id=7)

    with patch.object(music_mod.asyncio, "sleep", new_callable=AsyncMock):
        with patch("bot.commands.music.IDLE_LEAVE_SECONDS", 0):
            with patch("bot.commands.music._get_voice_client", return_value=vc):
                with patch(
                    "bot.commands.music._other_members_in_channel",
                    side_effect=[0, 1],
                ):
                    with patch("bot.commands.music._clear_queue") as cq:
                        with patch("bot.commands.music.logger"):
                            await cog._on_voice_state_update(member, before, after)
                            task = cog.bot._music_leave_tasks[GUILD_ID]
                            _ = await task
    vc.disconnect.assert_not_awaited()
    cq.assert_not_called()
    assert GUILD_ID not in cog.bot._music_leave_tasks


@pytest.mark.asyncio
async def test_idle_leave_task_disconnects_and_clears_queue(mock_bot, cog):
    from bot.commands import music as music_mod

    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    cog.bot._music_leave_tasks = {}
    ch = _channel(id_=5, members=[MagicMock(id=999)])
    vc = MagicMock(channel=ch, guild=ch.guild, disconnect=AsyncMock())
    cog.bot.voice_clients = [vc]
    cog.bot._music_queues = {GUILD_ID: deque([MagicMock()])}
    before = MagicMock(channel=ch)
    after = MagicMock(channel=None)
    member = MagicMock(id=7)

    with patch.object(music_mod.asyncio, "sleep", new_callable=AsyncMock):
        with patch("bot.commands.music.IDLE_LEAVE_SECONDS", 0):
            with patch("bot.commands.music._get_voice_client", return_value=vc):
                with patch("bot.commands.music._other_members_in_channel", return_value=0):
                    with patch("bot.commands.music._clear_queue") as cq:
                        with patch("bot.commands.music.logger"):
                            await cog._on_voice_state_update(member, before, after)
                            task = cog.bot._music_leave_tasks[GUILD_ID]
                            _ = await task
    vc.disconnect.assert_awaited()
    cq.assert_called_once_with(cog.bot, GUILD_ID)
    assert GUILD_ID not in cog.bot._music_leave_tasks


@pytest.mark.asyncio
async def test_idle_leave_skips_disconnect_when_channel_repopulated(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    cog.bot._music_leave_tasks = {}
    ch = _channel(id_=5, members=[MagicMock(id=999)])
    vc = MagicMock(channel=ch, guild=ch.guild, disconnect=AsyncMock())
    cog.bot.voice_clients = [vc]
    before = MagicMock(channel=ch)
    after = MagicMock(channel=None)
    member = MagicMock(id=7)

    async def instant_sleep(_):
        return None

    om = MagicMock(side_effect=[0, 1])

    with patch("bot.commands.music.asyncio.sleep", instant_sleep):
        with patch("bot.commands.music.IDLE_LEAVE_SECONDS", 0):
            with patch("bot.commands.music._get_voice_client", return_value=vc):
                with patch("bot.commands.music._other_members_in_channel", om):
                    with patch("bot.commands.music._clear_queue") as cq:
                        with patch("bot.commands.music.logger"):
                            await cog._on_voice_state_update(member, before, after)
                            await cog.bot._music_leave_tasks[GUILD_ID]
    vc.disconnect.assert_not_called()
    cq.assert_not_called()


@pytest.mark.asyncio
async def test_idle_leave_skips_disconnect_when_voice_client_gone(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    mock_bot.db_pool = None
    cog.bot._music_leave_tasks = {}
    ch = _channel(id_=5, members=[MagicMock(id=999)])
    vc = MagicMock(channel=ch, guild=ch.guild, disconnect=AsyncMock())
    cog.bot.voice_clients = [vc]
    before = MagicMock(channel=ch)
    after = MagicMock(channel=None)
    member = MagicMock(id=7)

    async def instant_sleep(_):
        return None

    with patch("bot.commands.music.asyncio.sleep", instant_sleep):
        with patch("bot.commands.music.IDLE_LEAVE_SECONDS", 0):
            with patch("bot.commands.music._get_voice_client", return_value=None):
                with patch("bot.commands.music._other_members_in_channel", return_value=0):
                    with patch("bot.commands.music._clear_queue") as cq:
                        with patch("bot.commands.music.logger"):
                            await cog._on_voice_state_update(member, before, after)
                            await cog.bot._music_leave_tasks[GUILD_ID]
    vc.disconnect.assert_not_called()
    cq.assert_not_called()


@pytest.mark.asyncio
async def test_voice_state_bot_moves_non_voice_channel_skips_music_binding(mock_bot, cog):
    mock_bot.settings.feature_music = True
    mock_bot.db_pool = MagicMock()
    mock_bot.user = MagicMock(id=999)
    member = MagicMock(id=999, guild=MagicMock(id=GUILD_ID))
    before = MagicMock(channel=MagicMock(id=10))
    after = MagicMock(channel=MagicMock(id=11))
    with patch("bot.commands.music.set_music_voice_channel", AsyncMock()) as sm:
        with patch("bot.commands.music._is_voice_or_stage", return_value=False):
            await cog._on_voice_state_update(member, before, after)
    sm.assert_not_called()
