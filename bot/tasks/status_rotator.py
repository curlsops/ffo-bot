"""Rotating status with daily dad jokes."""

import logging
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

DAD_JOKE_API = "https://icanhazdadjoke.com/"
DISCORD_ACTIVITY_NAME_MAX_LEN = 128


class StatusRotator(commands.Cog):
    """Updates the bot's presence with a random dad joke daily."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        if getattr(self.bot.settings, "feature_rotating_status", False):
            self.rotate_status.start()
            logger.info("Status rotator started")
        else:
            logger.debug("Status rotator disabled (feature_rotating_status=false)")

    async def cog_unload(self) -> None:
        self.rotate_status.cancel()

    async def _fetch_dad_joke(self) -> Optional[str]:
        """Fetch a random dad joke from icanhazdadjoke.com."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    DAD_JOKE_API,
                    headers={"Accept": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Dad joke API returned {resp.status}")
                        return None
                    data = await resp.json()
                    joke = data.get("joke", "").strip()
                    return joke if joke else None
        except Exception as e:
            logger.warning(f"Failed to fetch dad joke: {e}")
            return None

    @tasks.loop(hours=1)
    async def rotate_status(self) -> None:
        """Update bot presence with a random dad joke."""
        joke = await self._fetch_dad_joke()
        if not joke:
            return

        if len(joke) > DISCORD_ACTIVITY_NAME_MAX_LEN:
            joke = joke[: DISCORD_ACTIVITY_NAME_MAX_LEN - 3] + "..."

        activity = discord.Activity(
            type=discord.ActivityType.playing,
            name=joke,
        )
        try:
            await self.bot.change_presence(activity=activity)
            logger.info("Updated status: %s", joke[:60] + ("..." if len(joke) > 60 else ""))
        except Exception as e:
            logger.error(f"Failed to update presence: {e}")

    @rotate_status.before_loop
    async def before_rotate(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatusRotator(bot))
