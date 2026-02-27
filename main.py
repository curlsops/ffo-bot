#!/usr/bin/env python3
"""
FFO Discord Bot - Main Entry Point

High-availability Discord bot for automated reactions, media archival,
and community management.
"""

import asyncio
import logging
import signal
import sys

from bot.client import FFOBot
from config.logging_config import setup_logging
from config.settings import Settings

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Handle graceful shutdown signals."""

    def __init__(self, bot: FFOBot):
        self.bot = bot
        self.shutdown_initiated = False

    def setup_signals(self):
        """Register signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._shutdown(s)))

        logger.info("Signal handlers registered for graceful shutdown")

    async def _shutdown(self, sig):
        """Handle shutdown signal."""
        if self.shutdown_initiated:
            logger.warning("Shutdown already in progress")
            return

        self.shutdown_initiated = True
        logger.info(f"Received signal {sig.name}, initiating graceful shutdown...")

        try:
            # Close bot (includes message draining and cleanup)
            await self.bot.close()
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}", exc_info=True)

        # Stop event loop
        loop = asyncio.get_event_loop()
        loop.stop()


async def main():
    """Main application entry point."""
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        print(f"Failed to load settings: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    setup_logging(log_level=settings.log_level, log_format=settings.log_format)

    logger.info("=" * 60)
    logger.info("FFO Discord Bot Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Log Level: {settings.log_level}")
    logger.info(f"Media Storage: {settings.media_storage_path}")

    # Create bot instance
    bot = FFOBot(settings)

    # Setup graceful shutdown
    shutdown_handler = GracefulShutdown(bot)
    shutdown_handler.setup_signals()

    # Start bot
    try:
        async with bot:
            await bot.start(settings.discord_bot_token)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
