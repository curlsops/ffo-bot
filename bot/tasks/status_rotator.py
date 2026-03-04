import logging

import aiohttp
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

DAD_JOKE_API = "https://icanhazdadjoke.com/"
MAX_ACTIVITY_LEN = 128


class StatusRotator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        if getattr(self.bot.settings, "feature_rotating_status", False):
            self.rotate_status.start()
            logger.info("Status rotator started")

    async def cog_unload(self):
        self.rotate_status.cancel()

    async def _fetch_joke(self):
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    DAD_JOKE_API, headers={"Accept": "application/json"}
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    joke = data.get("joke", "").strip()
                    return joke or None
        except Exception as e:
            logger.debug("Status rotator joke fetch failed: %s", e)
            return None

    @tasks.loop(hours=1)
    async def rotate_status(self):
        joke = await self._fetch_joke()
        if not joke:
            return
        if len(joke) > MAX_ACTIVITY_LEN:
            joke = joke[: MAX_ACTIVITY_LEN - 3] + "..."
        try:
            await self.bot.change_presence(activity=discord.CustomActivity(name=joke))
        except Exception as e:
            logger.debug("Status rotator change_presence failed: %s", e)

    @rotate_status.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusRotator(bot))
