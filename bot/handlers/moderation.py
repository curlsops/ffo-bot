import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ModerationHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _should_notify(self, guild_id: int) -> bool:
        return bool(
            self.bot.notifier is not None
            and self.bot.settings.feature_notify_moderation
            and guild_id
        )

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
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                    if entry.target and entry.target.id == user.id:
                        moderator_id = entry.user.id if entry.user else None
                        if entry.reason:
                            reason = entry.reason
                        break
            except discord.Forbidden:  # no audit log permission
                pass
            await self.bot.notifier.notify_moderation(
                guild.id, "Member Banned", user.id, moderator_id, reason=reason
            )
        except Exception as e:
            logger.warning("moderation notify ban failed: %s", e)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if not self._should_notify(guild.id):
            return
        try:
            await self.bot.notifier.notify_moderation(guild.id, "Member Unbanned", user.id, None)
        except Exception as e:
            logger.warning("moderation notify unban failed: %s", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self._should_notify(member.guild.id):
            return
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id:
                    await self.bot.notifier.notify_moderation(
                        member.guild.id,
                        "Member Kicked",
                        member.id,
                        entry.user.id if entry.user else None,
                        reason=entry.reason,
                    )
                    return
        except discord.Forbidden:  # no audit log permission
            pass
        except Exception as e:
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
            if before.communication_disabled_until != after.communication_disabled_until:
                await self._notify_timeout_change(before, after)
        except Exception as e:
            logger.warning("moderation notify member update failed: %s", e)

    async def _notify_nickname_change(self, before: discord.Member, after: discord.Member):
        try:
            async for entry in before.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.member_update
            ):
                if entry.target and entry.target.id == before.id:
                    extra = f"`{before.nick or '(none)'}` → `{after.nick or '(none)'}`"
                    await self.bot.notifier.notify_moderation(
                        before.guild.id,
                        "Nickname Changed",
                        before.id,
                        entry.user.id if entry.user else None,
                        extra=extra,
                    )
                    return
        except discord.Forbidden:  # no audit log permission
            pass

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
        try:
            async for entry in before.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.member_update
            ):
                if entry.target and entry.target.id == before.id:
                    moderator_id = entry.user.id if entry.user else None
                    reason = entry.reason
                    break
        except discord.Forbidden:  # no audit log permission
            pass
        if after.communication_disabled_until:
            extra = f"Until <t:{int(after.communication_disabled_until.timestamp())}:F>"
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
                if before.server_mute != after.server_mute:
                    action = "Server Muted" if after.server_mute else "Server Unmuted"
                    await self._notify_voice_mod_action(
                        member.guild, member.id, action, after.channel or before.channel
                    )
                elif before.server_deaf != after.server_deaf:
                    action = "Server Deafened" if after.server_deaf else "Server Undeafened"
                    await self._notify_voice_mod_action(
                        member.guild, member.id, action, after.channel or before.channel
                    )
            elif before.channel and not after.channel:
                await self._notify_voice_disconnect(member, before)
        except Exception as e:
            logger.warning("moderation notify voice state failed: %s", e)

    async def _notify_voice_mod_action(
        self, guild: discord.Guild, target_id: int, action: str, channel
    ):
        moderator_id = None
        try:
            async for entry in guild.audit_logs(
                limit=5, action=discord.AuditLogAction.member_update
            ):
                if entry.target and entry.target.id == target_id:
                    moderator_id = entry.user.id if entry.user else None
                    break
        except discord.Forbidden:  # no audit log permission
            pass
        channel_name = getattr(channel, "name", "?")
        extra = f"Channel: #{channel_name}"
        await self.bot.notifier.notify_moderation(
            guild.id, action, target_id, moderator_id, extra=extra
        )

    async def _notify_voice_disconnect(self, member: discord.Member, before: discord.VoiceState):
        try:
            async for entry in member.guild.audit_logs(
                limit=3, action=discord.AuditLogAction.member_disconnect
            ):
                if (
                    entry.created_at
                    and (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5
                ):
                    moderator_id = entry.user.id if entry.user else None
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
        except discord.Forbidden:  # no audit log permission
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or not self._should_notify(message.guild.id):
            return
        if message.author and message.author.bot:
            return
        try:
            moderator_id = None
            try:
                async for entry in message.guild.audit_logs(
                    limit=5, action=discord.AuditLogAction.message_delete
                ):
                    ch = getattr(getattr(entry, "extra", None), "channel", None)
                    if ch and ch.id == message.channel.id:
                        moderator_id = entry.user.id if entry.user else None
                        break
            except discord.Forbidden:  # no audit log permission
                pass
            content = (message.content or "(no text)")[:200]
            if message.attachments:
                content += f" [+{len(message.attachments)} attachment(s)]"
            extra = f"Channel: <#{message.channel.id}>\nContent: {content}"
            action = "Message Deleted" if moderator_id else "Message Deleted (self or unknown)"
            await self.bot.notifier.notify_moderation(
                message.guild.id,
                action,
                message.author.id if message.author else 0,
                moderator_id,
                extra=extra,
            )
        except Exception as e:
            logger.warning("moderation notify message delete failed: %s", e)

    @commands.Cog.listener()
    async def on_bulk_message_delete(
        self, messages: list[discord.Message], channel: discord.ChannelType
    ):
        if not channel.guild or not self._should_notify(channel.guild.id):
            return
        try:
            moderator_id = None
            try:
                async for entry in channel.guild.audit_logs(
                    limit=5, action=discord.AuditLogAction.message_bulk_delete
                ):
                    moderator_id = entry.user.id if entry.user else None
                    break
            except discord.Forbidden:  # no audit log permission
                pass
            extra = f"Channel: <#{channel.id}>\nCount: {len(messages)} messages"
            await self.bot.notifier.notify_moderation(
                channel.guild.id,
                "Bulk Message Delete",
                0,
                moderator_id,
                extra=extra,
            )
        except Exception as e:
            logger.warning("moderation notify bulk delete failed: %s", e)


async def setup(bot):
    await bot.add_cog(ModerationHandler(bot))
