#!/usr/bin/env python3
import asyncio
import importlib.metadata
import logging
import os
import signal
import sys

from bot.client import FFOBot
from config.logging_config import setup_logging
from config.settings import Settings

logger = logging.getLogger(__name__)


class GracefulShutdown:
    def __init__(self, bot: FFOBot):
        self.bot = bot
        self.shutdown_initiated = False

    def setup_signals(self):
        loop = asyncio.get_event_loop()

        def make_handler(s: int):
            def handler() -> None:
                asyncio.create_task(self._shutdown(s))

            return handler

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, make_handler(sig))

    async def _shutdown(self, sig):
        if self.shutdown_initiated:
            return
        self.shutdown_initiated = True
        logger.info(f"Received {sig.name}")
        try:
            await self.bot.close()
        except Exception as e:
            logger.error(f"Shutdown error: {e}", exc_info=True)


async def main():
    try:
        settings = Settings()
    except Exception as e:
        print(f"Settings error: {e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(log_level=settings.log_level, log_format=settings.log_format)
    try:
        version = os.environ.get("FFO_BOT_VERSION") or importlib.metadata.version("ffo-bot")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    logger.info("Starting v%s (env=%s)", version, settings.environment)

    bot = FFOBot(settings)
    GracefulShutdown(bot).setup_signals()

    try:
        async with bot:
            await bot.start(settings.discord_bot_token)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal: {e}", file=sys.stderr)
        sys.exit(1)
