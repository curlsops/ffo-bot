import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mafic import SearchType
from mafic.errors import PlayerNotConnected

from bot.commands.music import (
    MusicCommands,
    MusicGroup,
    _clear_queue,
    _format_duration,
    _get_queue,
    _other_members_in_channel,
    _play_next,
)
from bot.utils.music import _ms, _music_embed, _time_until_track, _track_label

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
        cog.bot._music_queues = {GUILD_ID: queue}
    return i, p


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.pool = MagicMock()
    bot.permission_checker = MagicMock()
    bot.permission_checker.check_role = AsyncMock(return_value=True)
    bot.user = MagicMock(id=999)
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


class TestQueueHelpers:
    def test_get_queue_creates_defaultdict(self, mock_bot):
        if hasattr(mock_bot, "_music_queues"):
            del mock_bot._music_queues
        q = _get_queue(mock_bot, 123)
        assert q == [] and 123 in mock_bot._music_queues

    def test_clear_queue(self, mock_bot):
        mock_bot._music_queues = {1: [MagicMock()]}
        _clear_queue(mock_bot, 1)
        assert 1 not in mock_bot._music_queues

    def test_clear_queue_not_present_no_op(self, mock_bot):
        mock_bot._music_queues = {1: []}
        _clear_queue(mock_bot, 2)
        assert 1 in mock_bot._music_queues


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
        mock_bot._music_queues = {GUILD_ID: queue}
        player.play = AsyncMock()
        result = await _play_next(player)
        assert result is expected
        if called:
            player.play.assert_called_once_with(track)
            assert mock_bot._music_queues[GUILD_ID] == []
        else:
            player.play.assert_not_called()


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
        with patch(f"bot.commands.music.{resolver}", AsyncMock(return_value=search_query)):
            with _patch_player():
                await cog.music_group.play.callback(cog.music_group, i, url)
        player.fetch_tracks.assert_called_once_with(search_query, search_type=SearchType.YOUTUBE)
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
                "spotify_playlist_to_search_queries",
                "https://open.spotify.com/playlist/5bCeKZhm0Vrk4cOydmil2N",
                ["Yuka Kitamura - Slave Knight Gael", "Yuka Kitamura - Soul of Cinder"],
            ),
        ],
    )
    async def test_play_playlist_queues_tracks(self, cog, resolver, url, queries):
        t1, t2 = MagicMock(title="A"), MagicMock(title="B")
        i, player = _play_ctx(cog, fetch_side_effect=[[t1], [t2]])
        with patch(f"bot.commands.music.{resolver}", AsyncMock(return_value=queries)):
            with _patch_player():
                await cog.music_group.play.callback(cog.music_group, i, url)
        assert player.fetch_tracks.call_count == 2
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
    async def test_play_spotify_url_plays_first_result_no_picker(self, cog):
        t1, t2 = MagicMock(title="Slave Knight Gael"), MagicMock(
            title="Slave Knight Gael [Extended]"
        )
        i, player = _play_ctx(cog, tracks=[t1, t2])
        with patch(
            "bot.commands.music.spotify_url_to_search_query",
            AsyncMock(return_value="Yuka Kitamura - Slave Knight Gael"),
        ):
            with _patch_player():
                await cog.music_group.play.callback(
                    cog.music_group, i, "https://open.spotify.com/track/74m8PoL6GZulfVzeYS6W0C"
                )
        player.play.assert_called_once_with(t1)
        assert i.followup.send.call_args[1].get("view") is None

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


class TestMusicStop:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "members,preserve,substr",
        [
            ([MagicMock(id=1), MagicMock(id=999)], True, "preserved"),
            ([MagicMock(id=999)], False, "left"),
        ],
    )
    async def test_stop(self, cog, members, preserve, substr):
        ch = _channel(members=members)
        player = MagicMock(channel=ch, stop=AsyncMock(), disconnect=AsyncMock())
        cog.bot._music_queues = {GUILD_ID: [MagicMock(title="Queued")]}
        i = _interaction(cog.bot, voice_channel=MagicMock())
        i.guild.voice_client = player
        with _patch_player():
            await cog.music_group.stop.callback(cog.music_group, i)
        player.stop.assert_called_once()
        assert (
            GUILD_ID in cog.bot._music_queues and len(cog.bot._music_queues[GUILD_ID]) == 1
        ) == preserve
        if not preserve:
            player.disconnect.assert_called_once()
        assert substr in i.followup.send.call_args[1]["embed"].description.lower()


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
        cog.bot._music_queues = {GUILD_ID: [MagicMock()] * queue_len}
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
        cog.bot._music_queues = {GUILD_ID: []}
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
