import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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


class TestMusicLeave:
    @pytest.mark.asyncio
    async def test_leave_not_connected(self, cog):
        i = _interaction(cog.bot)
        i.guild.voice_client = None
        cog.bot.voice_clients = []
        await cog.music_group.leave.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        assert "Not in" in i.followup.send.call_args[0][0]


class TestMusicQueue:
    @pytest.mark.asyncio
    async def test_queue_empty(self, cog):
        i = _interaction(cog.bot)
        i.guild.voice_client = None
        cog.bot._music_queues = {1: []}
        await cog.music_group.queue_cmd.callback(cog.music_group, i)
        i.followup.send.assert_called_once()
        assert "empty" in i.followup.send.call_args[0][0].lower()


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
