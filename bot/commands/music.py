from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from mafic import EndReason, Player, SearchType, Track, TrackEndEvent

if TYPE_CHECKING:
    from bot.client import FFOBot

logger = logging.getLogger(__name__)

QUEUE_MAX_DISPLAY = 10
MAX_QUERY_LEN = 200


def _format_duration(ms: int) -> str:
    if ms <= 0:
        return "live"
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _get_queue(bot: FFOBot, guild_id: int) -> list[Track]:
    if not hasattr(bot, "_music_queues"):
        bot._music_queues = defaultdict(list)
    return bot._music_queues[guild_id]


def _clear_queue(bot: FFOBot, guild_id: int) -> None:
    if hasattr(bot, "_music_queues") and guild_id in bot._music_queues:
        del bot._music_queues[guild_id]


async def _play_next(player: Player) -> bool:
    bot = player.client
    queue = _get_queue(bot, player.guild.id)
    if not queue:
        return False
    track = queue.pop(0)
    await player.play(track)
    return True


@app_commands.guild_only()
class MusicGroup(app_commands.Group):
    def __init__(self, cog: "MusicCommands"):
        super().__init__(name="music", description="Music playback via Lavalink")
        self.cog = cog

    @app_commands.command(name="join", description="Join your voice channel")
    async def join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Join a voice channel first.", ephemeral=True)
            return
        bot = interaction.client
        if not bot.pool:
            await interaction.followup.send("Music is not enabled.", ephemeral=True)
            return
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            if interaction.guild.voice_client.channel.id == channel.id:
                await interaction.followup.send("Already in your channel.")
                return
            await interaction.guild.voice_client.disconnect()
        await channel.connect(cls=Player)
        await interaction.followup.send(f"Joined {channel.mention}.")

    @app_commands.command(name="play", description="Play a track (URL or search query)")
    @app_commands.describe(query="YouTube/Spotify URL or search query")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=False)
        query = query.strip()[:MAX_QUERY_LEN]
        if not query:
            await interaction.followup.send("Provide a URL or search query.", ephemeral=True)
            return
        bot = interaction.client
        if not bot.pool:
            await interaction.followup.send("Music is not enabled.", ephemeral=True)
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Join a voice channel first.", ephemeral=True)
            return
        channel = interaction.user.voice.channel
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await channel.connect(cls=Player)
            player = interaction.guild.voice_client
        if player.channel.id != channel.id:
            await interaction.followup.send(
                "Join the same voice channel as the bot.", ephemeral=True
            )
            return
        is_url = query.startswith("http://") or query.startswith("https://")
        search_type = None if is_url else SearchType.YOUTUBE
        result = await player.fetch_tracks(query, search_type=search_type)
        if result is None:
            await interaction.followup.send("No results found.", ephemeral=True)
            return
        if isinstance(result, list):
            tracks = result
            playlist = False
        else:
            tracks = result.tracks
            playlist = True
        if not tracks:
            await interaction.followup.send("No tracks found.", ephemeral=True)
            return
        queue = _get_queue(bot, interaction.guild_id)
        if player.current:
            queue.extend(tracks)
            count = len(tracks)
            if playlist:
                await interaction.followup.send(f"Queued playlist ({count} tracks).")
            else:
                await interaction.followup.send(
                    f"Queued: **{tracks[0].title}**"
                    + (f" (+{count - 1} more)" if count > 1 else "")
                )
        else:
            await player.play(tracks[0])
            if len(tracks) > 1:
                queue.extend(tracks[1:])
            if playlist:
                await interaction.followup.send(
                    f"Playing playlist: **{tracks[0].title}** (+{len(tracks) - 1} queued)"
                )
            else:
                await interaction.followup.send(f"Playing: **{tracks[0].title}**")

    @app_commands.command(name="leave", description="Disconnect from voice")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if not interaction.guild.voice_client:
            await interaction.followup.send("Not in a voice channel.")
            return
        _clear_queue(interaction.client, interaction.guild_id)
        await interaction.guild.voice_client.disconnect()
        await interaction.followup.send("Left voice channel.")

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send("Nothing playing.", ephemeral=True)
            return
        if player.paused:
            await interaction.followup.send("Already paused.")
            return
        await player.pause()
        await interaction.followup.send("Paused.")

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send("Nothing playing.", ephemeral=True)
            return
        if not player.paused:
            await interaction.followup.send("Not paused.")
            return
        await player.resume()
        await interaction.followup.send("Resumed.")

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send("Nothing playing.", ephemeral=True)
            return
        await player.stop()
        if await _play_next(player):
            await interaction.followup.send("Skipped. Playing next.")
        else:
            await interaction.followup.send("Skipped.")

    @app_commands.command(name="queue", description="Show the queue")
    async def queue_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = interaction.guild.voice_client
        queue = _get_queue(interaction.client, interaction.guild_id)
        current = player.current if (player and isinstance(player, Player)) else None
        if not current and not queue:
            await interaction.followup.send("Queue is empty.", ephemeral=True)
            return
        lines = []
        if current:
            dur = _format_duration(current.length)
            lines.append(f"**Now:** {current.title} ({dur})")
        for i, t in enumerate(queue[:QUEUE_MAX_DISPLAY], 1):
            dur = _format_duration(t.length)
            lines.append(f"{i}. {t.title} ({dur})")
        if len(queue) > QUEUE_MAX_DISPLAY:
            lines.append(f"... +{len(queue) - QUEUE_MAX_DISPLAY} more")
        await interaction.followup.send("\n".join(lines), ephemeral=True)


class MusicCommands(commands.Cog):
    def __init__(self, bot: FFOBot):
        self.bot = bot
        self.music_group = MusicGroup(self)
        self.bot.tree.add_command(self.music_group)

    @commands.Cog.listener("track_end")
    async def _on_track_end(self, event: TrackEndEvent) -> None:
        if event.reason != EndReason.FINISHED:
            return
        if await _play_next(event.player):
            logger.debug("Playing next track in queue for guild %s", event.player.guild.id)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command("music")


async def setup(bot: FFOBot) -> None:
    await bot.add_cog(MusicCommands(bot))
