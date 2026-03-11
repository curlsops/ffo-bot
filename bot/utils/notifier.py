import logging
import traceback
from collections.abc import Sequence

import discord

from bot.utils.config_repair import repair_servers_config
from bot.utils.discord_helpers import get_or_fetch_channel
from config.constants import Constants

logger = logging.getLogger(__name__)

CACHE_KEY = "notify_channel:{server_id}"
TB_MAX = 1016  # 1024 limit; "```\n"+tb+"\n```" adds 8


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "…" if len(s) > max_len else s


def _format_traceback(exc: Exception, max_len: int = TB_MAX) -> str:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return tb[-(max_len - 3) :] + "..." if len(tb) > max_len else tb


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
        result = int(cfg["notify_channel_id"]) if cfg and cfg.get("notify_channel_id") else None
        if self.bot.cache:
            self.bot.cache.set(
                cache_key, result if result is not None else -1, ttl=Constants.CACHE_TTL
            )
        return result

    async def get_notify_channel(self, server_id: int) -> discord.TextChannel | None:
        channel_id = await self.get_notify_channel_id(server_id)
        if not channel_id:
            return None
        ch = await get_or_fetch_channel(self.bot, channel_id)
        if ch is None:
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

    async def _notify(
        self,
        server_id: int,
        title: str,
        desc: str,
        color: discord.Color,
        fields: Sequence[tuple[str, str | None, bool]] | None = None,
        footer: str | None = None,
    ) -> bool:
        embed = discord.Embed(title=title, description=desc, color=color)
        for name, value, inline in fields or []:
            if value is not None:
                embed.add_field(name=name, value=str(value)[:1024] or "—", inline=inline)
        if footer:
            embed.set_footer(text=footer)
        return await self.send(server_id, embed)

    async def notify_giveaway_created(
        self, server_id: int, prize: str, host_id: int, channel_id: int, ends_at
    ):
        fields = [
            ("Host", f"<@{host_id}>", True),
            ("Channel", f"<#{channel_id}>", True),
            ("Ends", f"<t:{int(ends_at.timestamp())}:R>", True),
        ]
        await self._notify(
            server_id, "Giveaway Created", f"**{prize}**", discord.Color.green(), fields
        )

    async def notify_giveaway_ended(
        self, server_id: int, prize: str, winners: list, entry_count: int
    ):
        w = ", ".join(f"<@{x}>" for x in winners) if winners else "No valid entries"
        await self._notify(
            server_id,
            "Giveaway Ended",
            f"**{prize}**",
            discord.Color.blue(),
            [("Entries", str(entry_count), True), ("Winners", w, False)],
        )

    async def notify_error(
        self,
        server_id: int,
        error: Exception,
        context: str,
        user_id: int | None = None,
        channel_id: int | None = None,
    ):
        fields = [
            ("Type", type(error).__name__, True),
            ("Message", str(error)[:1024] or "No message", False),
            ("User", f"<@{user_id}>" if user_id else None, True),
            ("Channel", f"<#{channel_id}>" if channel_id else None, True),
            ("Traceback", f"```\n{_format_traceback(error)}\n```", False),
        ]
        await self._notify(server_id, "Error", f"**{context}**", discord.Color.red(), fields)

    async def notify_quotebook_submitted(
        self, server_id: int, quote_text: str, submitter_id: int, quote_id: str
    ):
        await self._notify(
            server_id,
            "Quote Submitted",
            _truncate(quote_text, 200),
            discord.Color.gold(),
            [("Submitter", f"<@{submitter_id}>", True), ("Quote ID", f"`{quote_id[:8]}`", True)],
            "Use /quote approve to approve",
        )

    async def notify_permission_changed(
        self,
        server_id: int,
        action: str,
        role: str,
        target_id: int | None,
        changed_by_id: int,
        discord_role: int | None = None,
    ):
        role_val = (
            f"<@&{discord_role}>" if discord_role else ("Cleared" if action == "Set role" else None)
        )
        fields = [
            ("Target", f"<@{target_id}>" if target_id else None, True),
            ("By", f"<@{changed_by_id}>", True),
            ("Role", role_val, True),
        ]
        await self._notify(
            server_id, "Permission Changed", f"**{action}** {role}", discord.Color.blue(), fields
        )

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
        jump = f"[Jump](https://discord.com/channels/{server_id}/{channel_id}/{message_id})"
        await self._notify(
            server_id,
            "Reaction Role",
            f"**{action}**: {emoji} → <@&{role_id}>",
            discord.Color.purple(),
            [("Message", jump, True), ("By", f"<@{created_by_id}>", True)],
        )

    async def notify_faq_changed(self, server_id: int, action: str, topic: str, changed_by_id: int):
        await self._notify(
            server_id,
            "FAQ Changed",
            f"**{action}**: {topic}",
            discord.Color.green(),
            [("By", f"<@{changed_by_id}>", True)],
        )

    async def notify_notify_channel_changed(
        self, server_id: int, channel_id: int | None, changed_by_id: int
    ):
        desc = f"Notifications set to <#{channel_id}>" if channel_id else "Notifications disabled"
        await self._notify(
            server_id,
            "Notify Channel Changed",
            desc,
            discord.Color.blue(),
            [("By", f"<@{changed_by_id}>", True)],
        )

    async def notify_rate_limit_hit(
        self, server_id: int, user_id: int, reason: str, command_name: str
    ):
        await self._notify(
            server_id,
            "Rate Limit Hit",
            reason[:256],
            discord.Color.orange(),
            [("User", f"<@{user_id}>", True), ("Command", command_name, True)],
        )

    async def notify_bot_added(self, server_id: int, server_name: str, member_count: int):
        await self._notify(
            server_id,
            "Bot Added to Server",
            f"**{server_name}**",
            discord.Color.green(),
            [("Server ID", str(server_id), True), ("Members", str(member_count), True)],
        )

    async def notify_moderation(
        self,
        server_id: int,
        action: str,
        target_id: int,
        moderator_id: int | None,
        reason: str | None = None,
        extra: str | None = None,
    ):
        fields = [
            ("Target", f"<@{target_id}>", True),
            ("By", f"<@{moderator_id}>" if moderator_id else None, True),
            ("Reason", reason[:1024] if reason else None, False),
            ("Details", extra[:1024] if extra else None, False),
        ]
        await self._notify(
            server_id, "Moderation", f"**{action}**", discord.Color.dark_red(), fields
        )

    async def notify_faq_submission(
        self, server_id: int, question: str, submitter_id: int, submission_id: str
    ):
        await self._notify(
            server_id,
            "FAQ Question Submitted",
            _truncate(question, 300),
            discord.Color.gold(),
            [("Submitter", f"<@{submitter_id}>", True), ("ID", f"`{submission_id[:8]}`", True)],
            "Use /faq add to create an entry from this",
        )
