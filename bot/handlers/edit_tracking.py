import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class EditTrackingHandler(commands.Cog):
    def __init__(self, bot: commands.Bot, edit_tracker):
        self.bot = bot
        self.edit_tracker = edit_tracker

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content or not after.content or after.author.bot:
            return
        if not after.guild:
            return
        entry = self.edit_tracker.get(before.id, before.channel.id)
        if not entry:
            return
        channel = self.bot.get_channel(entry.channel_id)
        if not channel:
            return
        try:
            response_msg = await channel.fetch_message(entry.response_msg_id)
        except discord.NotFound:
            self.edit_tracker.untrack(before.id, before.channel.id)
            return
        prefix = self.bot.command_prefix
        if isinstance(prefix, str):
            prefix = (prefix,)
        content = after.content.strip()
        used_prefix = None
        for p in prefix:
            if content.startswith(p):
                used_prefix = p
                break
        if not used_prefix:
            return
        new_content = content[len(used_prefix) :].strip()
        if not new_content:
            return
        parts = new_content.split(maxsplit=1)
        cmd_name = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""
        try:
            await response_msg.edit(content=f"*(edited)* `{used_prefix}{cmd_name} {args_str}`")
        except discord.HTTPException as e:
            logger.warning("Edit track update failed: %s", e)


async def setup(bot):
    await bot.add_cog(EditTrackingHandler(bot, bot.edit_tracker))
