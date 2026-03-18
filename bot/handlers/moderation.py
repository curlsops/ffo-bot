import logging
from asyncio import Lock
from datetime import datetime, timezone
from time import monotonic

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ModerationHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._audit_logs_cache: dict[
            tuple[int, discord.AuditLogAction, str, int], tuple[float, list]
        ] = {}
        self._audit_logs_locks: dict[tuple[int, discord.AuditLogAction, str, int], Lock] = {}
        self._audit_logs_ttl_seconds = 1.0

    def _should_notify(self, guild_id: int) -> bool:
        return bool(
            self.bot.notifier is not None
            and self.bot.settings.feature_notify_moderation
            and guild_id
        )

    async def _get_audit_logs(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        cache_scope: str,
        *,
        limit: int,
    ) -> list:
        key = (guild.id, action, cache_scope, limit)
        now = monotonic()
        cached = self._audit_logs_cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        lock = self._audit_logs_locks.setdefault(key, Lock())
        async with lock:
            now = monotonic()
            cached = self._audit_logs_cache.get(key)
            if cached is not None and cached[0] > now:
                return cached[1]
            try:
                entries = [entry async for entry in guild.audit_logs(limit=limit, action=action)]
            except discord.Forbidden:  # no audit log permission
                entries = []
            self._audit_logs_cache[key] = (now + self._audit_logs_ttl_seconds, entries)
            self._prune_audit_logs_cache()
            return entries

    def _prune_audit_logs_cache(self) -> None:
        if len(self._audit_logs_cache) <= 64:
            return
        now = monotonic()
        expired = [
            key for key, (expires_at, _) in self._audit_logs_cache.items() if expires_at <= now
        ]
        for key in expired:
            self._audit_logs_cache.pop(key, None)
            self._audit_logs_locks.pop(key, None)

    async def _find_audit_log_entry(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        cache_scope: str,
        matcher,
        *,
        limit: int,
    ):
        entries = await self._get_audit_logs(guild, action, cache_scope, limit=limit)
        for entry in entries:
            if matcher(entry):
                return entry
        return None

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        if not self._should_notify(guild.id):
            return
        try:
            reason = "No reason given"
            moderator_id = None
            try:
                ban = await guild.fetch_ban(user)
                reason = ban.reason or reason
            except discord.NotFound:  # no ban record (race)
                pass
            try:
                entry = await self._find_audit_log_entry(
                    guild,
                    discord.AuditLogAction.ban,
                    f"ban:{user.id}",
                    lambda e: bool(e.target and e.target.id == user.id),
                    limit=5,
                )
                if entry:
                    moderator_id = entry.user.id if entry.user else None
                    if entry.reason:
                        reason = entry.reason
            except discord.Forbidden:  # no audit log permission
                pass
            await self.bot.notifier.notify_moderation(
                guild.id, "Member Banned", user.id, moderator_id, reason=reason
            )
        except discord.HTTPException as e:
            logger.warning("moderation notify ban failed: %s", e)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if not self._should_notify(guild.id):
            return
        try:
            await self.bot.notifier.notify_moderation(guild.id, "Member Unbanned", user.id, None)
        except discord.HTTPException as e:
            logger.warning("moderation notify unban failed: %s", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self._should_notify(member.guild.id):
            return
        try:
            entry = await self._find_audit_log_entry(
                member.guild,
                discord.AuditLogAction.kick,
                f"kick:{member.id}",
                lambda e: bool(e.target and e.target.id == member.id),
                limit=5,
            )
            if entry:
                await self.bot.notifier.notify_moderation(
                    member.guild.id,
                    "Member Kicked",
                    member.id,
                    entry.user.id if entry.user else None,
                    reason=entry.reason,
                )
                return
        except discord.HTTPException as e:
            logger.warning("moderation notify kick failed: %s", e)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not self._should_notify(before.guild.id):
            return
        try:
            if before.nick != after.nick:
                await self._notify_nickname_change(before, after)
                return
            if before.name != after.name or before.global_name != after.global_name:
                await self._notify_username_change(before, after)
                return
            before_timeout = getattr(before, "timed_out_until", None)
            after_timeout = getattr(after, "timed_out_until", None)
            if before_timeout != after_timeout:
                await self._notify_timeout_change(before, after)
        except discord.HTTPException as e:
            logger.warning("moderation notify member update failed: %s", e)

    async def _notify_nickname_change(self, before: discord.Member, after: discord.Member):
        entry = await self._find_audit_log_entry(
            before.guild,
            discord.AuditLogAction.member_update,
            f"member_update:{before.id}",
            lambda e: bool(e.target and e.target.id == before.id),
            limit=5,
        )
        if entry:
            extra = f"`{before.nick or '(none)'}` → `{after.nick or '(none)'}`"
            await self.bot.notifier.notify_moderation(
                before.guild.id,
                "Nickname Changed",
                before.id,
                entry.user.id if entry.user else None,
                extra=extra,
            )
            return

    async def _notify_username_change(self, before: discord.Member, after: discord.Member):
        parts = []
        if before.name != after.name:
            parts.append(f"name: `{before.name}` → `{after.name}`")
        if before.global_name != after.global_name:
            parts.append(
                f"display: `{before.global_name or '(none)'}` → `{after.global_name or '(none)'}`"
            )
        extra = "; ".join(parts) if parts else None
        await self.bot.notifier.notify_moderation(
            before.guild.id,
            "Discord Username Changed",
            before.id,
            None,
            extra=extra,
        )

    async def _notify_timeout_change(self, before: discord.Member, after: discord.Member):
        moderator_id = None
        reason = None
        entry = await self._find_audit_log_entry(
            before.guild,
            discord.AuditLogAction.member_update,
            f"member_update:{before.id}",
            lambda e: bool(e.target and e.target.id == before.id),
            limit=5,
        )
        if entry:
            moderator_id = entry.user.id if entry.user else None
            reason = entry.reason
        after_timeout = getattr(after, "timed_out_until", None)
        if after_timeout:
            extra = f"Until <t:{int(after_timeout.timestamp())}:F>"
            await self.bot.notifier.notify_moderation(
                before.guild.id,
                "Member Timed Out",
                before.id,
                moderator_id,
                reason=reason,
                extra=extra,
            )
        else:
            await self.bot.notifier.notify_moderation(
                before.guild.id,
                "Member Timeout Removed",
                before.id,
                moderator_id,
                reason=reason,
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if not self._should_notify(member.guild.id):
            return
        try:
            if before.channel == after.channel:
                before_mute = getattr(before, "mute", False)
                after_mute = getattr(after, "mute", False)
                before_deaf = getattr(before, "deaf", False)
                after_deaf = getattr(after, "deaf", False)
                if before_mute != after_mute:
                    action = "Server Muted" if after_mute else "Server Unmuted"
                    await self._notify_voice_mod_action(
                        member.guild, member.id, action, after.channel or before.channel
                    )
                elif before_deaf != after_deaf:
                    action = "Server Deafened" if after_deaf else "Server Undeafened"
                    await self._notify_voice_mod_action(
                        member.guild, member.id, action, after.channel or before.channel
                    )
            elif before.channel and not after.channel:
                await self._notify_voice_disconnect(member, before)
        except discord.HTTPException as e:
            logger.warning("moderation notify voice state failed: %s", e)

    async def _notify_voice_mod_action(
        self, guild: discord.Guild, target_id: int, action: str, channel
    ):
        moderator_id = None
        entry = await self._find_audit_log_entry(
            guild,
            discord.AuditLogAction.member_update,
            f"member_update:{target_id}",
            lambda e: bool(e.target and e.target.id == target_id),
            limit=5,
        )
        if entry:
            moderator_id = entry.user.id if entry.user else None
        if moderator_id is None or moderator_id == target_id:
            return
        channel_name = getattr(channel, "name", "?")
        extra = f"Channel: #{channel_name}"
        await self.bot.notifier.notify_moderation(
            guild.id, action, target_id, moderator_id, extra=extra
        )

    async def _notify_voice_disconnect(self, member: discord.Member, before: discord.VoiceState):
        entry = await self._find_audit_log_entry(
            member.guild,
            discord.AuditLogAction.member_disconnect,
            f"member_disconnect:{member.id}",
            lambda e: bool(
                e.created_at and (datetime.now(timezone.utc) - e.created_at).total_seconds() < 5
            ),
            limit=3,
        )
        if entry:
            moderator_id = entry.user.id if entry.user else None
            if moderator_id is None or moderator_id == member.id:
                return
            channel_name = before.channel.name if before.channel else "?"
            extra = f"From #{channel_name}"
            await self.bot.notifier.notify_moderation(
                member.guild.id,
                "Voice Disconnected",
                member.id,
                moderator_id,
                extra=extra,
            )
            return

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or not self._should_notify(message.guild.id):
            return
        if message.author and message.author.bot:
            return
        try:
            moderator_id = None
            entry = await self._find_audit_log_entry(
                message.guild,
                discord.AuditLogAction.message_delete,
                f"message_delete:{message.channel.id}",
                lambda e: bool(
                    (ch := getattr(getattr(e, "extra", None), "channel", None))
                    and ch.id == message.channel.id
                ),
                limit=5,
            )
            if entry:
                moderator_id = entry.user.id if entry.user else None
            if moderator_id is None:
                return
            author_id = message.author.id if message.author else 0
            if moderator_id == author_id:
                return
            content = (message.content or "(no text)")[:200]
            if message.attachments:
                content += f" [+{len(message.attachments)} attachment(s)]"
            extra = f"Channel: <#{message.channel.id}>\nContent: {content}"
            await self.bot.notifier.notify_moderation(
                message.guild.id,
                "Message Deleted",
                author_id,
                moderator_id,
                extra=extra,
            )
        except discord.HTTPException as e:
            logger.warning("moderation notify message delete failed: %s", e)

    @commands.Cog.listener()
    async def on_bulk_message_delete(
        self, messages: list[discord.Message], channel: discord.ChannelType
    ):
        if not channel.guild or not self._should_notify(channel.guild.id):
            return
        try:
            moderator_id = None
            entry = await self._find_audit_log_entry(
                channel.guild,
                discord.AuditLogAction.message_bulk_delete,
                f"bulk_delete:{channel.id}",
                lambda _: True,
                limit=5,
            )
            if entry:
                moderator_id = entry.user.id if entry.user else None
            extra = f"Channel: <#{channel.id}>\nCount: {len(messages)} messages"
            await self.bot.notifier.notify_moderation(
                channel.guild.id,
                "Bulk Message Delete",
                0,
                moderator_id,
                extra=extra,
            )
        except discord.HTTPException as e:
            logger.warning("moderation notify bulk delete failed: %s", e)


async def setup(bot):
    await bot.add_cog(ModerationHandler(bot))
