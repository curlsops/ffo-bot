from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from mafic import EndReason, Player, SearchType, Track, TrackEndEvent
from mafic.errors import PlayerNotConnected

from bot.auth.permissions import PermissionContext
from bot.services.spotify import (
    spotify_playlist_to_search_queries,
    spotify_url_to_search_query,
)
from bot.services.tidal import tidal_playlist_to_search_queries, tidal_url_to_search_query
from config.constants import Constants, Role

if TYPE_CHECKING:
    from bot.client import FFOBot

logger = logging.getLogger(__name__)

QUEUE_PAGE_SIZE = 5
MAX_QUERY_LEN = 200
IDLE_LEAVE_SECONDS = 30
TRACK_PICKER_MAX = 5
TRACK_PICKER_LABEL_MAX = 50
EMBED_COLOR = 0x9B59B6
CONNECTION_FAILED_MSG = "Music connection failed. Try /music leave then /music join again."


def _get_voice_client(guild: discord.Guild, bot: "FFOBot"):
    vc = guild.voice_client
    if vc is None:
        vc = discord.utils.get(bot.voice_clients, guild=guild)
    return vc


def _other_members_in_channel(channel: discord.VoiceChannel, bot_user_id: int) -> int:
    return sum(1 for m in channel.members if m.id != bot_user_id)


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
    try:
        await player.play(track)
    except PlayerNotConnected:
        queue.insert(0, track)
        return False
    return True


def _music_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR,
    )


async def _fetch_playlist_tracks(player: Player, queries: list[str]) -> list[Track]:
    tracks: list[Track] = []
    for sq in queries:
        result = await player.fetch_tracks(sq, search_type=SearchType.YOUTUBE)
        if result and isinstance(result, list) and result:
            tracks.append(result[0])
        elif result and not isinstance(result, list) and result.tracks:
            tracks.append(result.tracks[0])
    return tracks


def _track_label(track: Track, i: int) -> str:
    author = getattr(track, "author", None) or ""
    parts = [author, track.title] if author else [track.title]
    label = " – ".join(p for p in parts if p)
    return (f"{i}. {label}" if label else f"{i}. {track.title}")[:TRACK_PICKER_LABEL_MAX]


def _time_until_track(
    player: Player | None,
    current: Track | None,
    queue: list[Track],
    idx: int,
) -> str:
    def _ms(v) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    if idx == 0:
        if not current or not player:
            return "—"
        pos_ms = _ms(getattr(player, "position", None))
        length_ms = _ms(getattr(current, "length", None))
        left_ms = max(0, length_ms - pos_ms)
        return _format_duration(left_ms) + " left"
    cumulative_ms = 0
    if current and player:
        pos_ms = _ms(getattr(player, "position", None))
        length_ms = _ms(getattr(current, "length", None))
        cumulative_ms = max(0, length_ms - pos_ms)
    for i in range(idx - 1):
        cumulative_ms += _ms(getattr(queue[i], "length", None))
    return "in " + _format_duration(cumulative_ms)


class _MusicQueueView(discord.ui.View):
    def __init__(
        self,
        player: Player | None,
        current: Track | None,
        queue: list[Track],
        per_page: int = QUEUE_PAGE_SIZE,
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.player = player
        self.current = current
        self.queue = queue
        self.per_page = per_page
        self.page = 0
        rows: list[tuple[Track, str, int]] = []
        if current:
            rows.append((current, "Now", 0))
        for i, t in enumerate(queue, 1):
            rows.append((t, str(i), i))
        self.rows = rows
        self._max_page = max(0, (len(rows) - 1) // per_page)

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id="mq:prev",
            row=0,
        )
        prev_btn.callback = self._prev_callback
        self.add_item(prev_btn)

        self.page_btn = discord.ui.Button(
            label="1/1",
            style=discord.ButtonStyle.primary,
            custom_id="mq:page",
            disabled=True,
            row=0,
        )
        self.add_item(self.page_btn)

        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id="mq:next",
            row=0,
        )
        next_btn.callback = self._next_callback
        self.add_item(next_btn)
        self._update_buttons()

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self._max_page + 1}"
        for child in self.children:
            if child.custom_id == "mq:prev":
                child.disabled = self.page <= 0
            elif child.custom_id == "mq:next":
                child.disabled = self.page >= self._max_page

    def _format_page(self) -> discord.Embed:
        start = self.page * self.per_page
        chunk = self.rows[start : start + self.per_page]
        lines: list[str] = []
        for track, label, idx in chunk:
            dur = _format_duration(track.length)
            time_info = _time_until_track(self.player, self.current, self.queue, idx)
            link = f"[{track.title}]({track.uri})" if track.uri else track.title
            lines.append(f"**#{label}** {link} ({dur}) · {time_info}")
        desc = "\n".join(lines)
        if len(desc) > Constants.DISCORD_MESSAGE_LIMIT - 100:
            desc = desc[: Constants.DISCORD_MESSAGE_LIMIT - 120] + "\n\n...(truncated)"
        return _music_embed("🎵 Music Queue", desc or "—")

    async def _prev_callback(self, interaction: discord.Interaction):
        if self.page <= 0:
            return
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._format_page(), view=self)

    async def _next_callback(self, interaction: discord.Interaction):
        if self.page >= self._max_page:
            return
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._format_page(), view=self)


class _ResumeView(discord.ui.View):
    def __init__(self, player: Player, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.player = player

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.success, row=0)
    async def resume_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self.player.paused:
            await interaction.response.defer()
            return
        await self.player.resume()
        for child in self.children:
            child.disabled = True
        embed = _music_embed("▶️ Resumed", "")
        await interaction.response.edit_message(embed=embed, view=self)


class TrackPickerView(discord.ui.View):
    def __init__(
        self,
        tracks: list[Track],
        player: Player,
        bot: "FFOBot",
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.tracks = tracks[:TRACK_PICKER_MAX]
        self.player = player
        self.bot = bot
        self._chosen = False
        for i, t in enumerate(self.tracks):
            btn = discord.ui.Button(
                label=_track_label(t, i + 1),
                style=discord.ButtonStyle.secondary,
                custom_id=f"music:pick:{i}",
                row=i // 5,
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, idx: int):
        async def cb(interaction: discord.Interaction):
            if self._chosen:
                await interaction.response.defer(ephemeral=True)
                return
            self._chosen = True
            track = self.tracks[idx]
            try:
                await self.player.play(track)
            except PlayerNotConnected:
                await interaction.response.send_message(
                    CONNECTION_FAILED_MSG,
                    ephemeral=True,
                )
                return
            embed = _music_embed("🎵 Playing", f"▶️ **{track.title}**")
            await interaction.response.edit_message(embed=embed, view=None)

        return cb


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
        try:
            await channel.connect(cls=Player)
        except TimeoutError:
            await interaction.followup.send(
                "Voice connection timed out. Try again.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=_music_embed("🎵 Joined", f"Connected to {channel.mention}.")
        )

    @app_commands.command(name="play", description="Play a track (URL or search query)")
    @app_commands.describe(
        query="YouTube URL (incl. playlists), Tidal URL, Spotify URL (track/playlist), or search query",
        force_next="Play next in queue (mod+ only)",
    )
    async def play(self, interaction: discord.Interaction, query: str, force_next: bool = False):
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
            try:
                await channel.connect(cls=Player)
            except TimeoutError:
                await interaction.followup.send(
                    "Voice connection timed out. Try again.",
                    ephemeral=True,
                )
                return
            player = interaction.guild.voice_client
        if player.channel.id != channel.id:
            await interaction.followup.send(
                "Join the same voice channel as the bot.", ephemeral=True
            )
            return
        is_url = query.startswith("http://") or query.startswith("https://")
        search_type = None if is_url else SearchType.YOUTUBE
        tracks = None
        playlist = False
        from_resolved_url = False
        if is_url and "tidal.com" in query.lower():
            playlist_queries = await tidal_playlist_to_search_queries(query)
            if playlist_queries:
                tracks = await _fetch_playlist_tracks(player, playlist_queries)
                playlist = True
            else:
                search_query = await tidal_url_to_search_query(query)
                if search_query:
                    query = search_query
                    search_type = SearchType.YOUTUBE
                    from_resolved_url = True
                else:
                    await interaction.followup.send(
                        "Could not resolve Tidal link. Try searching by song name.",
                        ephemeral=True,
                    )
                    return
        elif is_url and "spotify.com" in query.lower():
            settings = getattr(bot, "settings", None)
            cid = getattr(settings, "spotify_client_id", None) if settings else None
            csec = getattr(settings, "spotify_client_secret", None) if settings else None
            playlist_queries = await spotify_playlist_to_search_queries(query, cid, csec)
            if playlist_queries:
                tracks = await _fetch_playlist_tracks(player, playlist_queries)
                playlist = True
            else:
                search_query = await spotify_url_to_search_query(query)
                if search_query:
                    query = search_query
                    search_type = SearchType.YOUTUBE
                    from_resolved_url = True
                else:
                    await interaction.followup.send(
                        "Could not resolve Spotify link. Try searching by song name.",
                        ephemeral=True,
                    )
                    return
        if tracks is None:
            result = await player.fetch_tracks(query, search_type=search_type)
            if result is None:
                await interaction.followup.send("No results found.", ephemeral=True)
                return
            if isinstance(result, list):
                tracks = result
            else:
                tracks = result.tracks
                playlist = True
        if not tracks:
            await interaction.followup.send("No tracks found.", ephemeral=True)
            return
        if force_next:
            ctx = PermissionContext(
                server_id=interaction.guild_id or 0,
                user_id=interaction.user.id,
                command_name="music play",
            )
            if not await bot.permission_checker.check_role(ctx, Role.MODERATOR):
                await interaction.followup.send(
                    "Moderator or higher required for force play next.",
                    ephemeral=True,
                )
                return
        queue = _get_queue(bot, interaction.guild_id)
        if not playlist and len(tracks) > 1 and not from_resolved_url:
            lines = [
                f"**{i + 1}.** {getattr(t, 'author', '') or ''} – {t.title}"
                for i, t in enumerate(tracks[:TRACK_PICKER_MAX])
            ]
            embed = _music_embed("🎵 Pick a track", "\n".join(lines))
            view = TrackPickerView(tracks, player, bot)
            await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True,
            )
            return
        if player.current:
            count = len(tracks)
            if force_next:
                queue[:0] = tracks
                start_pos = 1
            else:
                start_pos = len(queue) + 1
                queue.extend(tracks)
            if playlist:
                pos_range = (
                    f"#{start_pos}–#{start_pos + count - 1}" if count > 1 else f"#{start_pos}"
                )
                desc = f"Added {count} tracks at {pos_range}."
            else:
                pos = f"#{start_pos}"
                desc = f"**{tracks[0].title}** at position {pos}"
                if count > 1:
                    desc += f" (+{count - 1} more at #{start_pos + 1}–#{start_pos + count - 1})"
                desc += "."
            if force_next:
                desc += " (playing next)"
            embed = _music_embed("📥 Queued", desc)
            if player.paused:
                await interaction.followup.send(embed=embed, view=_ResumeView(player))
            else:
                await interaction.followup.send(embed=embed)
        else:
            try:
                await player.play(tracks[0])
            except PlayerNotConnected:
                await interaction.followup.send(CONNECTION_FAILED_MSG, ephemeral=True)
                return
            if len(tracks) > 1:
                queue.extend(tracks[1:])
            if playlist:
                desc = f"▶️ **{tracks[0].title}**\n📥 +{len(tracks) - 1} queued"
                await interaction.followup.send(embed=_music_embed("🎵 Playing", desc))
            else:
                desc = f"▶️ **{tracks[0].title}**"
                await interaction.followup.send(embed=_music_embed("🎵 Playing", desc))

    @app_commands.command(name="leave", description="Disconnect from voice")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        vc = _get_voice_client(interaction.guild, interaction.client)
        if not vc:
            await interaction.followup.send("Not in a voice channel.", ephemeral=True)
            return
        channel_name = vc.channel.name if vc.channel else "voice"
        _clear_queue(interaction.client, interaction.guild_id)
        await _cancel_leave_task(_get_leave_tasks(interaction.client), interaction.guild_id)
        await vc.disconnect()
        await interaction.followup.send(
            embed=_music_embed("👋 Left", f"Disconnected from {channel_name}.")
        )

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send("Nothing playing.", ephemeral=True)
            return
        if player.paused:
            await interaction.followup.send(embed=_music_embed("⏸️ Already paused", ""))
            return
        await player.pause()
        title = player.current.title if player.current else "Track"
        await interaction.followup.send(embed=_music_embed("⏸️ Paused", f"**{title}**"))

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send("Nothing playing.", ephemeral=True)
            return
        if not player.paused:
            await interaction.followup.send(embed=_music_embed("▶️ Not paused", ""))
            return
        await player.resume()
        title = player.current.title if player.current else "Track"
        await interaction.followup.send(embed=_music_embed("▶️ Resumed", f"**{title}**"))

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send("Nothing playing.", ephemeral=True)
            return
        skipped_title = player.current.title if player.current else None
        await player.stop()
        if await _play_next(player):
            next_title = player.current.title if player.current else None
            desc = f"Skipped **{skipped_title}**.\n▶️ Now playing: **{next_title}**"
            await interaction.followup.send(embed=_music_embed("⏭️ Skipped", desc))
        else:
            desc = f"Skipped **{skipped_title}**." if skipped_title else "Skipped."
            await interaction.followup.send(embed=_music_embed("⏭️ Skipped", desc))

    @app_commands.command(name="stop", description="Stop playback (queue preserved)")
    async def stop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send("Nothing playing.", ephemeral=True)
            return
        await player.stop()
        others = (
            _other_members_in_channel(player.channel, interaction.client.user.id)
            if player.channel and interaction.client.user
            else 0
        )
        if others == 0:
            _clear_queue(interaction.client, interaction.guild_id)
            await _cancel_leave_task(_get_leave_tasks(interaction.client), interaction.guild_id)
            await player.disconnect()
            await interaction.followup.send(
                embed=_music_embed("⏹️ Stopped", "Left and cleared queue.")
            )
        else:
            await interaction.followup.send(embed=_music_embed("⏹️ Stopped", "Queue preserved."))

    @app_commands.command(name="clear-queue", description="[Admin] Clear the queue")
    @app_commands.default_permissions(administrator=True)
    async def clear_queue(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._check_admin(interaction, "music clear-queue"):
            return
        queue = _get_queue(interaction.client, interaction.guild_id)
        if not queue:
            await interaction.followup.send(
                embed=_music_embed("🎵 Clear Queue", "Queue is already empty."),
                ephemeral=True,
            )
            return
        count = len(queue)
        _clear_queue(interaction.client, interaction.guild_id)
        await interaction.followup.send(
            embed=_music_embed("🎵 Queue Cleared", f"Removed {count} track(s)."),
            ephemeral=True,
        )

    @app_commands.command(
        name="force-play", description="[Admin] Force play a track at queue position"
    )
    @app_commands.describe(position="Queue position (1 = next in queue)")
    @app_commands.default_permissions(administrator=True)
    async def force_play(self, interaction: discord.Interaction, position: int):
        await interaction.response.defer(ephemeral=False)
        if not await self.cog._check_admin(interaction, "music force-play"):
            return
        if position < 1:
            await interaction.followup.send(
                "Position must be at least 1.",
                ephemeral=True,
            )
            return
        player = interaction.guild.voice_client
        if not player or not isinstance(player, Player):
            await interaction.followup.send(
                "Not in a voice channel.",
                ephemeral=True,
            )
            return
        queue = _get_queue(interaction.client, interaction.guild_id)
        idx = position - 1
        if idx >= len(queue):
            await interaction.followup.send(
                f"No track at position {position}. Queue has {len(queue)} item(s).",
                ephemeral=True,
            )
            return
        track = queue.pop(idx)
        current = player.current
        if current:
            queue.insert(0, current)
            await player.stop()
        try:
            await player.play(track)
        except PlayerNotConnected:
            queue.insert(0, track)
            await interaction.followup.send(CONNECTION_FAILED_MSG, ephemeral=True)
            return
        await interaction.followup.send(
            embed=_music_embed("🎵 Force Playing", f"▶️ **{track.title}**")
        )

    @app_commands.command(name="queue", description="Show the queue")
    async def queue_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = interaction.guild.voice_client
        queue = _get_queue(interaction.client, interaction.guild_id)
        current = player.current if (player and isinstance(player, Player)) else None
        if not current and not queue:
            await interaction.followup.send(
                embed=_music_embed("🎵 Queue", "Queue is empty."),
                ephemeral=True,
            )
            return
        view = _MusicQueueView(player, current, queue)
        await interaction.followup.send(
            embed=view._format_page(),
            view=view,
            ephemeral=True,
        )


def _get_leave_tasks(bot: FFOBot) -> dict[int, asyncio.Task]:
    if not hasattr(bot, "_music_leave_tasks"):
        bot._music_leave_tasks = {}
    return bot._music_leave_tasks


async def _cancel_leave_task(tasks: dict[int, asyncio.Task], guild_id: int) -> None:
    if guild_id not in tasks:
        return
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

    async def _check_admin(self, interaction: discord.Interaction, cmd: str) -> bool:
        if not interaction.guild_id:
            return False
        ctx = PermissionContext(
            server_id=interaction.guild_id,
            user_id=interaction.user.id,
            command_name=cmd,
        )
        if not await self.bot.permission_checker.check_role(ctx, Role.ADMIN):
            await interaction.followup.send("Admin required.", ephemeral=True)
            return False
        return True

    @commands.Cog.listener("on_voice_state_update")
    async def _on_voice_state_update(
        self, _member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
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
                            _clear_queue(self.bot, guild_id)
                            await vc.disconnect()
                            logger.info("Left voice channel %s (idle)", vc.channel.name)
                    tasks.pop(guild_id, None)

                await _cancel_leave_task(tasks, guild_id)
                tasks[guild_id] = asyncio.create_task(_leave_after_idle())

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
