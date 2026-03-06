import logging
import traceback

import discord

from bot.utils.config_repair import repair_servers_config

logger = logging.getLogger(__name__)


CACHE_KEY = "notify_channel:{server_id}"


class AdminNotifier:
    def __init__(self, bot):
        self.bot = bot

    async def get_notify_channel_id(self, server_id: int) -> int | None:
        cache_key = CACHE_KEY.format(server_id=server_id)
        if self.bot.cache:
            cached = self.bot.cache.get(cache_key)
            if cached is not None:
                return None if cached == -1 else cached
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT config FROM servers WHERE server_id = $1", server_id)
        cfg = repair_servers_config(row["config"]) if row and row["config"] is not None else None
        if not cfg:
            result = None
        elif channel_id := cfg.get("notify_channel_id"):
            result = int(channel_id)
        else:
            result = None
        if self.bot.cache:
            self.bot.cache.set(cache_key, result if result is not None else -1, ttl=300)
        return result

    async def get_notify_channel(self, server_id: int) -> discord.TextChannel | None:
        channel_id = await self.get_notify_channel_id(server_id)
        if not channel_id:
            return None
        ch = self.bot.get_channel(channel_id)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(channel_id)
            except Exception:
                logger.warning("Could not fetch notify channel %s", channel_id)
        return ch

    async def set_notify_channel(self, server_id: int, channel_id: int | None) -> bool:
        try:
            async with self.bot.db_pool.acquire() as conn:
                if channel_id:
                    await conn.execute(
                        "UPDATE servers SET config = COALESCE(config, '{}'::jsonb) || $1::jsonb, updated_at = NOW() WHERE server_id = $2",
                        {"notify_channel_id": channel_id},
                        server_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE servers SET config = config - 'notify_channel_id', updated_at = NOW() WHERE server_id = $1",
                        server_id,
                    )
            if self.bot.cache:
                self.bot.cache.delete(CACHE_KEY.format(server_id=server_id))
            return True
        except Exception:
            logger.exception("Failed to set notify channel")
            return False

    async def send(self, server_id: int, embed: discord.Embed) -> bool:
        channel = await self.get_notify_channel(server_id)
        if not channel:
            return False
        try:
            await channel.send(embed=embed)
            return True
        except Exception:
            logger.exception("Failed to send notification")
            return False

    async def notify_giveaway_created(
        self, server_id: int, prize: str, host_id: int, channel_id: int, ends_at
    ):
        embed = discord.Embed(
            title="Giveaway Created", description=f"**{prize}**", color=discord.Color.green()
        )
        embed.add_field(name="Host", value=f"<@{host_id}>", inline=True)
        embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
        embed.add_field(name="Ends", value=f"<t:{int(ends_at.timestamp())}:R>", inline=True)
        await self.send(server_id, embed)

    async def notify_giveaway_ended(
        self, server_id: int, prize: str, winners: list, entry_count: int
    ):
        embed = discord.Embed(
            title="Giveaway Ended", description=f"**{prize}**", color=discord.Color.blue()
        )
        embed.add_field(name="Entries", value=str(entry_count), inline=True)
        winners_val = ", ".join(f"<@{w}>" for w in winners) if winners else "No valid entries"
        embed.add_field(name="Winners", value=winners_val, inline=False)
        await self.send(server_id, embed)

    async def notify_error(
        self,
        server_id: int,
        error: Exception,
        context: str,
        user_id: int | None = None,
        channel_id: int | None = None,
    ):
        embed = discord.Embed(
            title="Error", description=f"**{context}**", color=discord.Color.red()
        )
        embed.add_field(name="Type", value=type(error).__name__, inline=True)
        embed.add_field(name="Message", value=str(error)[:1024] or "No message", inline=False)
        if user_id:
            embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
        if channel_id:
            embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        tb = tb[-1021:] + "..." if len(tb) > 1024 else tb
        embed.add_field(name="Traceback", value=f"```\n{tb}\n```", inline=False)
        await self.send(server_id, embed)

    async def notify_quotebook_submitted(
        self, server_id: int, quote_text: str, submitter_id: int, quote_id: str
    ):
        text = quote_text[:200] + "…" if len(quote_text) > 200 else quote_text
        embed = discord.Embed(
            title="Quote Submitted",
            description=text,
            color=discord.Color.gold(),
        )
        embed.add_field(name="Submitter", value=f"<@{submitter_id}>", inline=True)
        embed.add_field(name="Quote ID", value=f"`{quote_id[:8]}`", inline=True)
        embed.set_footer(text="Use /quote approve to approve")
        await self.send(server_id, embed)

    async def notify_permission_changed(
        self,
        server_id: int,
        action: str,
        role: str,
        target_id: int | None,
        changed_by_id: int,
        discord_role: int | None = None,
    ):
        embed = discord.Embed(
            title="Permission Changed",
            description=f"**{action}** {role}",
            color=discord.Color.blue(),
        )
        if target_id:
            embed.add_field(name="Target", value=f"<@{target_id}>", inline=True)
        embed.add_field(name="By", value=f"<@{changed_by_id}>", inline=True)
        if discord_role:
            embed.add_field(name="Role", value=f"<@&{discord_role}>", inline=True)
        elif action == "Set role":
            embed.add_field(name="Role", value="Cleared", inline=True)
        await self.send(server_id, embed)

    async def notify_reaction_role_setup(
        self,
        server_id: int,
        action: str,
        emoji: str,
        role_id: int,
        message_id: int,
        channel_id: int,
        created_by_id: int,
    ):
        embed = discord.Embed(
            title="Reaction Role",
            description=f"**{action}**: {emoji} → <@&{role_id}>",
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="Message",
            value=f"[Jump](https://discord.com/channels/{server_id}/{channel_id}/{message_id})",
            inline=True,
        )
        embed.add_field(name="By", value=f"<@{created_by_id}>", inline=True)
        await self.send(server_id, embed)

    async def notify_faq_changed(self, server_id: int, action: str, topic: str, changed_by_id: int):
        embed = discord.Embed(
            title="FAQ Changed",
            description=f"**{action}**: {topic}",
            color=discord.Color.green(),
        )
        embed.add_field(name="By", value=f"<@{changed_by_id}>", inline=True)
        await self.send(server_id, embed)

    async def notify_notify_channel_changed(
        self, server_id: int, channel_id: int | None, changed_by_id: int
    ):
        desc = f"Notifications set to <#{channel_id}>" if channel_id else "Notifications disabled"
        embed = discord.Embed(
            title="Notify Channel Changed",
            description=desc,
            color=discord.Color.blue(),
        )
        embed.add_field(name="By", value=f"<@{changed_by_id}>", inline=True)
        await self.send(server_id, embed)

    async def notify_rate_limit_hit(
        self, server_id: int, user_id: int, reason: str, command_name: str
    ):
        embed = discord.Embed(
            title="Rate Limit Hit",
            description=reason[:256],
            color=discord.Color.orange(),
        )
        embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
        embed.add_field(name="Command", value=command_name, inline=True)
        await self.send(server_id, embed)

    async def notify_bot_added(self, server_id: int, server_name: str, member_count: int):
        embed = discord.Embed(
            title="Bot Added to Server",
            description=f"**{server_name}**",
            color=discord.Color.green(),
        )
        embed.add_field(name="Server ID", value=str(server_id), inline=True)
        embed.add_field(name="Members", value=str(member_count), inline=True)
        await self.send(server_id, embed)

    async def notify_moderation(
        self,
        server_id: int,
        action: str,
        target_id: int,
        moderator_id: int | None,
        reason: str | None = None,
        extra: str | None = None,
    ):
        embed = discord.Embed(
            title="Moderation",
            description=f"**{action}**",
            color=discord.Color.dark_red(),
        )
        embed.add_field(name="Target", value=f"<@{target_id}>", inline=True)
        if moderator_id:
            embed.add_field(name="By", value=f"<@{moderator_id}>", inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason[:1024], inline=False)
        if extra:
            embed.add_field(name="Details", value=extra[:1024], inline=False)
        await self.send(server_id, embed)

    async def notify_faq_submission(
        self, server_id: int, question: str, submitter_id: int, submission_id: str
    ):
        text = question[:300] + "…" if len(question) > 300 else question
        embed = discord.Embed(
            title="FAQ Question Submitted",
            description=text,
            color=discord.Color.gold(),
        )
        embed.add_field(name="Submitter", value=f"<@{submitter_id}>", inline=True)
        embed.add_field(name="ID", value=f"`{submission_id[:8]}`", inline=True)
        embed.set_footer(text="Use /faq add to create an entry from this")
        await self.send(server_id, embed)
