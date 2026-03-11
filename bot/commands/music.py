from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands
from mafic import EndReason, Player, SearchType, Track, TrackEndEvent
from mafic.errors import PlayerNotConnected

from bot.auth.command_helpers import require_admin
from bot.auth.permissions import PermissionContext
from bot.services.spotify import (
    spotify_playlist_to_search_queries,
    spotify_url_to_search_query,
)
from bot.services.tidal import (
    tidal_mix_to_search_queries,
    tidal_playlist_to_search_queries,
    tidal_url_to_search_query,
)
from bot.utils.music import (
    EMBED_COLOR,
    _clear_queue,
    _format_duration,
    _get_queue,
    _music_embed,
    _time_until_track,
    _track_label,
)
from bot.utils.pagination import EmbedListPaginatedView
from config.constants import Role

if TYPE_CHECKING:
    from bot.client import FFOBot

logger = logging.getLogger(__name__)

QUEUE_PAGE_SIZE = 5
MAX_QUERY_LEN = 200
IDLE_LEAVE_SECONDS = 30
TRACK_PICKER_MAX = 5
CONNECTION_FAILED_MSG = "Music connection failed. Try /music leave then /music join again."


def _get_voice_client(guild: discord.Guild, bot: "FFOBot"):
    return guild.voice_client or discord.utils.get(bot.voice_clients, guild=guild)


def _other_members_in_channel(channel: discord.VoiceChannel, bot_user_id: int) -> int:
    return sum(1 for m in channel.members if m.id != bot_user_id)


async def _play_next(player: Player) -> bool:
    queue = _get_queue(player.client, player.guild.id)
    if not queue:
        return False
    track = queue.pop(0)
    try:
        await player.play(track)
    except PlayerNotConnected:
        queue.insert(0, track)
        return False
    return True


async def _fetch_playlist_tracks(player: Player, queries: list[str]) -> list[Track]:
    tracks: list[Track] = []
    for sq in queries:
        result = await player.fetch_tracks(sq, search_type=SearchType.YOUTUBE)
        if result and isinstance(result, list) and result:
            tracks.append(result[0])
        elif result and not isinstance(result, list) and result.tracks:
            tracks.append(result.tracks[0])
    return tracks


async def _resolve_url_tracks(
    player: Player, query: str, bot: "FFOBot"
) -> tuple[list[Track] | None, bool, str | None, str | None]:
    """Returns (tracks, is_playlist, resolved_search_query, error_msg)."""
    if "tidal.com" in query.lower() or "listen.tidal.com" in query.lower():
        pq = await tidal_playlist_to_search_queries(query)
        if not pq:
            pq = await tidal_mix_to_search_queries(query)
        if pq:
            return await _fetch_playlist_tracks(player, pq), True, None, None
        sq = await tidal_url_to_search_query(query)
        return (
            (None, False, sq, None)
            if sq
            else (None, False, None, "Could not resolve Tidal link. Try searching by song name.")
        )
    if "spotify.com" in query.lower():
        s = getattr(bot, "settings", None)
        cid, csec = (
            (getattr(s, "spotify_client_id", None), getattr(s, "spotify_client_secret", None))
            if s
            else (None, None)
        )
        pq = await spotify_playlist_to_search_queries(query, cid, csec)
        if pq:
            return await _fetch_playlist_tracks(player, pq), True, None, None
        sq = await spotify_url_to_search_query(query)
        return (
            (None, False, sq, None)
            if sq
            else (None, False, None, "Could not resolve Spotify link. Try searching by song name.")
        )
    return None, False, None, None


def _music_queue_format_row(
    row: tuple, player: Player | None, current: Track | None, queue: list[Track]
) -> str:
    t, lbl, idx = row
    link = f"[{t.title}]({t.uri})" if t.uri else t.title
    return f"**#{lbl}** {link} ({_format_duration(t.length)}) · {_time_until_track(player, current, queue, idx)}"


def _MusicQueueView(
    player: Player | None, current: Track | None, queue: list[Track]
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
        await i.followup.send(embed=_music_embed("🎵 Joined", f"Connected to {ch.mention}."))

    @app_commands.command(name="play", description="Play a track (URL or search query)")
    @app_commands.describe(
        query="YouTube URL (incl. playlists), Tidal URL (track/playlist/mix), Spotify URL (track/playlist), or search query",
        force_next="Play next in queue (mod+ only)",
    )
    async def play(self, i: discord.Interaction, query: str, force_next: bool = False):
        await i.response.defer(ephemeral=False)
        query = query.strip()[:MAX_QUERY_LEN]
        if not query:
            await i.followup.send("Provide a URL or search query.", ephemeral=True)
            return
        r = await _ensure_player(i)
        if r is None:
            return
        player, ch = r
        bot = i.client
        is_url = query.startswith(("http://", "https://"))
        search_type = None if is_url else SearchType.YOUTUBE
        tracks = None
        playlist = False
        from_resolved_url = False
        if is_url and (
            "tidal.com" in query.lower()
            or "listen.tidal.com" in query.lower()
            or "spotify.com" in query.lower()
        ):
            tracks, playlist, resolved_sq, err = await _resolve_url_tracks(player, query, bot)
            if err:
                await i.followup.send(err, ephemeral=True)
                return
            if resolved_sq:
                query, search_type, from_resolved_url = resolved_sq, SearchType.YOUTUBE, True
        if tracks is None:
            result = await player.fetch_tracks(query, search_type=search_type)
            if result is None:
                await i.followup.send("No results found.", ephemeral=True)
                return
            tracks = result if isinstance(result, list) else result.tracks
            if not isinstance(result, list):
                playlist = True
        if not tracks:
            await i.followup.send("No tracks found.", ephemeral=True)
            return
        if force_next:
            ctx = PermissionContext(
                server_id=i.guild_id or 0, user_id=i.user.id, command_name="music play"
            )
            if not await bot.permission_checker.check_role(ctx, Role.MODERATOR):
                await i.followup.send(
                    "Moderator or higher required for force play next.", ephemeral=True
                )
                return
        queue = _get_queue(bot, i.guild_id)
        if not playlist and len(tracks) > 1 and not from_resolved_url:
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
            count = len(tracks)
            if force_next:
                queue[:0] = tracks
                start_pos = 1
            else:
                start_pos = len(queue) + 1
                queue.extend(tracks)
            pr = f"#{start_pos}–#{start_pos + count - 1}" if count > 1 else f"#{start_pos}"
            desc = (
                f"Added {count} tracks at {pr}."
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
        else:
            try:
                await player.play(tracks[0])
            except PlayerNotConnected:
                await i.followup.send(CONNECTION_FAILED_MSG, ephemeral=True)
                return
            if len(tracks) > 1:
                queue.extend(tracks[1:])
            desc = f"▶️ **{tracks[0].title}**" + (
                f"\n📥 +{len(tracks) - 1} queued" if playlist else ""
            )
            await i.followup.send(embed=_music_embed("🎵 Playing", desc))

    @app_commands.command(name="leave", description="Disconnect from voice")
    async def leave(self, i: discord.Interaction):
        await i.response.defer(ephemeral=False)
        vc = _get_voice_client(i.guild, i.client)
        if not vc:
            await i.followup.send("Not in a voice channel.", ephemeral=True)
            return
        name = vc.channel.name if vc.channel else "voice"
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

    @app_commands.command(name="stop", description="Stop playback (queue preserved)")
    async def stop(self, i: discord.Interaction):
        await i.response.defer(ephemeral=False)
        if (p := await self._player_or_nothing(i)) is None:
            return
        await p.stop()
        others = (
            _other_members_in_channel(p.channel, i.client.user.id)
            if (p.channel and i.client.user)
            else 0
        )
        if others == 0:
            _clear_queue(i.client, i.guild_id)
            await _cancel_leave_task(_get_leave_tasks(i.client), i.guild_id)
            await p.disconnect()
            await i.followup.send(embed=_music_embed("⏹️ Stopped", "Left and cleared queue."))
        else:
            await i.followup.send(embed=_music_embed("⏹️ Stopped", "Queue preserved."))

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
        track = q.pop(idx)
        if p.current:
            q.insert(0, p.current)
            await p.stop()
        try:
            await p.play(track)
        except PlayerNotConnected:
            q.insert(0, track)
            await i.followup.send(CONNECTION_FAILED_MSG, ephemeral=True)
            return
        await i.followup.send(embed=_music_embed("🎵 Force Playing", f"▶️ **{track.title}**"))

    @app_commands.command(name="queue", description="Show the queue")
    async def queue_cmd(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
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
    return cast(dict[int, asyncio.Task[None]], getattr(bot, "_music_leave_tasks", {}))


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
