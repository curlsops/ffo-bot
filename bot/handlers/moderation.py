import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ModerationHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _should_notify(self, guild_id: int) -> bool:
        return (
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
            except discord.NotFound:
                pass
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                    if entry.target and entry.target.id == user.id:
                        moderator_id = entry.user.id if entry.user else None
                        if entry.reason:
                            reason = entry.reason
                        break
            except discord.Forbidden:
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
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.warning("moderation notify kick failed: %s", e)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not self._should_notify(before.guild.id):
            return
        if before.nick == after.nick:
            return
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
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.warning("moderation notify nickname failed: %s", e)


async def setup(bot):
    await bot.add_cog(ModerationHandler(bot))
