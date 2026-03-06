import asyncio
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
    def test_seconds(self):
        assert _format_duration(65000) == "1:05"

    def test_minutes(self):
        assert _format_duration(185000) == "3:05"

    def test_hours(self):
        assert _format_duration(3665000) == "1:01:05"

    def test_live(self):
        assert _format_duration(0) == "live"


class TestQueueHelpers:
    def test_get_queue_creates_defaultdict(self, mock_bot):
        if hasattr(mock_bot, "_music_queues"):
            del mock_bot._music_queues
        q = _get_queue(mock_bot, 123)
        assert q == []
        assert 123 in mock_bot._music_queues

    def test_clear_queue(self, mock_bot):
        mock_bot._music_queues = {1: [MagicMock()]}
        _clear_queue(mock_bot, 1)
        assert 1 not in mock_bot._music_queues


class TestPlayNext:
    @pytest.mark.asyncio
    async def test_play_next_empty_queue_returns_false(self, mock_bot):
        player = MagicMock(guild=MagicMock(id=1))
        player.client = mock_bot
        mock_bot._music_queues = {1: []}
        player.play = AsyncMock()
        result = await _play_next(player)
        assert result is False
        player.play.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_next_with_track_returns_true(self, mock_bot):
        track = MagicMock()
        player = MagicMock(guild=MagicMock(id=1))
        player.client = mock_bot
        mock_bot._music_queues = {1: [track]}
        player.play = AsyncMock()
        result = await _play_next(player)
        assert result is True
        player.play.assert_called_once_with(track)
        assert mock_bot._music_queues[1] == []


class TestMusicJoin:
    @pytest.mark.asyncio
    async def test_join_no_voice_channel(self, cog):
        i = _interaction(cog.bot)
        i.user.voice = None
        await cog.music_group.join.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        assert "voice channel" in i.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_join_music_disabled(self, cog):
        cog.bot.pool = None
        i = _interaction(cog.bot, voice_channel=MagicMock(id=99))
        await cog.music_group.join.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        assert "not enabled" in i.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_join_voice_connect_timeout(self, cog):
        channel = MagicMock(id=99)
        channel.connect = AsyncMock(side_effect=TimeoutError)
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = None
        await cog.music_group.join.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        assert "timed out" in i.followup.send.call_args[0][0].lower()
        assert i.followup.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_join_success_sends_embed(self, cog):
        channel = MagicMock(id=99)
        channel.mention = "#general"
        channel.connect = AsyncMock()
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = None
        await cog.music_group.join.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        call_kw = i.followup.send.call_args[1]
        assert call_kw.get("embed") is not None
        assert "Joined" in call_kw["embed"].title
        assert "general" in call_kw["embed"].description


class TestMusicPlay:
    @pytest.mark.asyncio
    async def test_play_empty_query(self, cog):
        i = _interaction(cog.bot, voice_channel=MagicMock(id=99))
        await cog.music_group.play.callback(cog.music_group, i, "   ")
        i.followup.send.assert_called_once()
        assert "URL or search" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_play_no_voice_channel(self, cog):
        i = _interaction(cog.bot)
        i.user.voice = None
        await cog.music_group.play.callback(cog.music_group, i, "never gonna give you up")
        i.followup.send.assert_called_once()
        assert "voice channel" in i.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_play_music_disabled(self, cog):
        cog.bot.pool = None
        i = _interaction(cog.bot, voice_channel=MagicMock(id=99))
        await cog.music_group.play.callback(cog.music_group, i, "test query")
        i.followup.send.assert_called_once()
        assert "not enabled" in i.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_play_voice_connect_timeout(self, cog):
        channel = MagicMock(id=99)
        channel.connect = AsyncMock(side_effect=TimeoutError)
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = None
        await cog.music_group.play.callback(cog.music_group, i, "never gonna give you up")
        i.followup.send.assert_called_once()
        assert "timed out" in i.followup.send.call_args[0][0].lower()
        assert i.followup.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_play_player_not_connected(self, cog):
        channel = MagicMock(id=99)
        player = MagicMock()
        player.channel = channel
        player.current = None
        player.fetch_tracks = AsyncMock(return_value=[MagicMock()])
        player.play = AsyncMock(side_effect=PlayerNotConnected)
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            await cog.music_group.play.callback(cog.music_group, i, "never gonna give you up")
        i.followup.send.assert_called_once()
        assert "music connection failed" in i.followup.send.call_args[0][0].lower()
        assert i.followup.send.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_play_tidal_url_resolved_to_youtube_search(self, cog):
        tidal_url = "https://tidal.com/track/110653480/u"
        search_query = "Excision & Dion Timmer - Time Stood Still"
        channel = MagicMock(id=99)
        track = MagicMock(title="Excision & Dion Timmer - Time Stood Still (Official Audio)")
        player = MagicMock()
        player.channel = channel
        player.current = None
        player.fetch_tracks = AsyncMock(return_value=[track])
        player.play = AsyncMock()
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch(
            "bot.commands.music.tidal_url_to_search_query", AsyncMock(return_value=search_query)
        ):
            with patch("bot.commands.music.Player", MagicMock):
                await cog.music_group.play.callback(cog.music_group, i, tidal_url)
        player.fetch_tracks.assert_called_once_with(search_query, search_type=SearchType.YOUTUBE)
        i.followup.send.assert_called_once()
        embed = i.followup.send.call_args[1].get("embed")
        assert embed is not None and "Playing" in embed.title

    @pytest.mark.asyncio
    async def test_play_tidal_playlist_queues_tracks(self, cog):
        tidal_playlist_url = "https://tidal.com/playlist/3f4f1385-aa86-46e5-a6ad-cb18248be3cd"
        channel = MagicMock(id=99)
        track1 = MagicMock(title="Dance Gavin Dance - Blood Wolf")
        track2 = MagicMock(title="Delta Heavy - Reborn")
        player = MagicMock()
        player.channel = channel
        player.current = None
        player.fetch_tracks = AsyncMock(
            side_effect=[
                [track1],
                [track2],
            ]
        )
        player.play = AsyncMock()
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch(
            "bot.commands.music.tidal_playlist_to_search_queries",
            AsyncMock(return_value=["Dance Gavin Dance - Blood Wolf", "Delta Heavy - Reborn"]),
        ):
            with patch("bot.commands.music.Player", MagicMock):
                await cog.music_group.play.callback(cog.music_group, i, tidal_playlist_url)
        assert player.fetch_tracks.call_count == 2
        i.followup.send.assert_called_once()
        embed = i.followup.send.call_args[1].get("embed")
        assert embed is not None and (
            "playlist" in (embed.description or "").lower()
            or "queued" in (embed.description or "").lower()
        )

    @pytest.mark.asyncio
    async def test_play_tidal_url_unresolvable(self, cog):
        tidal_url = "https://tidal.com/track/110653480/u"
        channel = MagicMock(id=99)
        player = MagicMock(channel=channel)
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            with patch(
                "bot.commands.music.tidal_url_to_search_query", AsyncMock(return_value=None)
            ):
                await cog.music_group.play.callback(cog.music_group, i, tidal_url)
        i.followup.send.assert_called_once()
        assert "Could not resolve Tidal" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_play_spotify_url_resolved_to_youtube_search(self, cog):
        spotify_url = "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
        search_query = "Michael Jackson - Billie Jean"
        channel = MagicMock(id=99)
        track = MagicMock(title="Billie Jean (Official Video)")
        player = MagicMock()
        player.channel = channel
        player.current = None
        player.fetch_tracks = AsyncMock(return_value=[track])
        player.play = AsyncMock()
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch(
            "bot.commands.music.spotify_url_to_search_query", AsyncMock(return_value=search_query)
        ):
            with patch("bot.commands.music.Player", MagicMock):
                await cog.music_group.play.callback(cog.music_group, i, spotify_url)
        player.fetch_tracks.assert_called_once_with(search_query, search_type=SearchType.YOUTUBE)
        i.followup.send.assert_called_once()
        embed = i.followup.send.call_args[1].get("embed")
        assert embed is not None and "Playing" in embed.title

    @pytest.mark.asyncio
    async def test_play_spotify_url_unresolvable(self, cog):
        spotify_url = "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
        channel = MagicMock(id=99)
        player = MagicMock(channel=channel)
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            with patch(
                "bot.commands.music.spotify_url_to_search_query", AsyncMock(return_value=None)
            ):
                await cog.music_group.play.callback(cog.music_group, i, spotify_url)
        i.followup.send.assert_called_once()
        assert "Could not resolve Spotify" in i.followup.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_play_queued_while_paused_includes_resume_button(self, cog):
        channel = MagicMock(id=99)
        track = MagicMock(title="Queued Song")
        player = MagicMock()
        player.channel = channel
        player.current = MagicMock(title="Now Playing")
        player.paused = True
        player.fetch_tracks = AsyncMock(return_value=[track])
        player.play = AsyncMock()
        cog.bot._music_queues = {1: []}
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            await cog.music_group.play.callback(cog.music_group, i, "another song")
        i.followup.send.assert_called_once()
        call_kw = i.followup.send.call_args[1]
        assert call_kw.get("view") is not None
        assert call_kw.get("embed") is not None
        assert "Queued" in call_kw["embed"].title

    @pytest.mark.asyncio
    async def test_play_multiple_results_shows_ephemeral_picker(self, cog):
        channel = MagicMock(id=99)
        track1 = MagicMock(title="Song A", author="Artist 1")
        track2 = MagicMock(title="Song B", author="Artist 2")
        player = MagicMock()
        player.channel = channel
        player.current = None
        player.fetch_tracks = AsyncMock(return_value=[track1, track2])
        player.play = AsyncMock()
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            await cog.music_group.play.callback(cog.music_group, i, "search query")
        i.followup.send.assert_called_once()
        call_kw = i.followup.send.call_args[1]
        assert call_kw.get("embed") is not None
        assert "Pick a track" in call_kw["embed"].title
        assert call_kw.get("view") is not None
        assert call_kw["ephemeral"] is True


class TestMusicStop:
    @pytest.mark.asyncio
    async def test_stop_preserves_queue_when_others_in_channel(self, cog):
        channel = MagicMock(id=99)
        channel.members = [MagicMock(id=1), MagicMock(id=999)]
        player = MagicMock()
        player.channel = channel
        player.stop = AsyncMock()
        cog.bot._music_queues = {1: [MagicMock(title="Queued")]}
        i = _interaction(cog.bot, voice_channel=MagicMock())
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            await cog.music_group.stop.callback(cog.music_group, i)
        player.stop.assert_called_once()
        assert 1 in cog.bot._music_queues
        assert len(cog.bot._music_queues[1]) == 1
        assert "preserved" in i.followup.send.call_args[1]["embed"].description

    @pytest.mark.asyncio
    async def test_stop_leaves_and_clears_when_no_others_in_channel(self, cog):
        channel = MagicMock(id=99)
        channel.members = [MagicMock(id=999)]
        player = MagicMock()
        player.channel = channel
        player.stop = AsyncMock()
        player.disconnect = AsyncMock()
        cog.bot._music_queues = {1: [MagicMock(title="Queued")]}
        i = _interaction(cog.bot, voice_channel=MagicMock())
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            await cog.music_group.stop.callback(cog.music_group, i)
        player.stop.assert_called_once()
        player.disconnect.assert_called_once()
        assert 1 not in cog.bot._music_queues
        assert "left" in i.followup.send.call_args[1]["embed"].description.lower()


class TestMusicLeave:
    @pytest.mark.asyncio
    async def test_leave_not_connected(self, cog):
        i = _interaction(cog.bot)
        i.guild.voice_client = None
        cog.bot.voice_clients = []
        await cog.music_group.leave.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        assert "Not in" in i.followup.send.call_args[0][0]


class TestMusicAdmin:
    @pytest.mark.asyncio
    async def test_clear_queue_admin(self, cog):
        cog.bot._music_queues = {1: [MagicMock(), MagicMock()]}
        i = _interaction(cog.bot)
        await cog.music_group.clear_queue.callback(cog.music_group, i)
        assert 1 not in cog.bot._music_queues
        embed = i.followup.send.call_args[1]["embed"]
        assert "Cleared" in embed.title
        assert "2" in embed.description

    @pytest.mark.asyncio
    async def test_clear_queue_empty(self, cog):
        cog.bot._music_queues = {1: []}
        i = _interaction(cog.bot)
        await cog.music_group.clear_queue.callback(cog.music_group, i)
        embed = i.followup.send.call_args[1]["embed"]
        assert "already empty" in embed.description

    @pytest.mark.asyncio
    async def test_force_play_position(self, cog):
        channel = MagicMock(id=99)
        track1 = MagicMock(title="Next")
        track2 = MagicMock(title="Forced")
        player = MagicMock()
        player.channel = channel
        player.current = MagicMock(title="Now Playing")
        player.stop = AsyncMock()
        player.play = AsyncMock()
        cog.bot._music_queues = {1: [track1, track2]}
        i = _interaction(cog.bot, voice_channel=channel)
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            await cog.music_group.force_play.callback(cog.music_group, i, 2)
        player.play.assert_called_once_with(track2)
        assert cog.bot._music_queues[1][0].title == "Now Playing"
        assert "Force Playing" in i.followup.send.call_args[1]["embed"].title


class TestMusicQueue:
    @pytest.mark.asyncio
    async def test_queue_empty(self, cog):
        i = _interaction(cog.bot)
        i.guild.voice_client = None
        cog.bot._music_queues = {1: []}
        await cog.music_group.queue_cmd.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        embed = i.followup.send.call_args[1].get("embed")
        assert embed is not None and "empty" in (embed.description or "").lower()

    @pytest.mark.asyncio
    async def test_queue_with_tracks_shows_paginated_links(self, cog):
        track = MagicMock()
        track.title = "Test Song"
        track.uri = "https://youtube.com/watch?v=abc"
        track.length = 180000
        player = MagicMock()
        player.current = track
        player.position = 0
        cog.bot._music_queues = {1: []}
        i = _interaction(cog.bot)
        i.guild.voice_client = player
        with patch("bot.commands.music.Player", MagicMock):
            await cog.music_group.queue_cmd.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        call_args = i.followup.send.call_args
        embed = call_args[1].get("embed")
        assert embed is not None
        assert "Music Queue" in embed.title
        assert "Test Song" in (embed.description or "")
        assert "youtube.com" in (embed.description or "")
        assert call_args[1].get("view") is not None


class TestOtherMembersInChannel:
    def test_excludes_bot(self):
        ch = MagicMock()
        ch.members = [MagicMock(id=1), MagicMock(id=2)]
        assert _other_members_in_channel(ch, 1) == 1

    def test_empty(self):
        ch = MagicMock()
        ch.members = []
        assert _other_members_in_channel(ch, 99) == 0


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
        channel = MagicMock(id=1)
        channel.members = [MagicMock(id=1), MagicMock(id=999)]
        channel.guild = MagicMock(id=1)
        vc = MagicMock(channel=channel, guild=channel.guild)
        cog.bot.voice_clients = [vc]
        task = asyncio.create_task(asyncio.sleep(60))
        cog.bot._music_leave_tasks = {1: task}
        await cog._on_voice_state_update(
            MagicMock(), MagicMock(channel=None), MagicMock(channel=channel)
        )
        assert 1 not in cog.bot._music_leave_tasks


class TestMusicCogUnload:
    @pytest.mark.asyncio
    async def test_cog_unload_removes_command(self, cog):
        cog.bot.tree.remove_command = MagicMock()
        await cog.cog_unload()
        cog.bot.tree.remove_command.assert_called_once_with("music")
