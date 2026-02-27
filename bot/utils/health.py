"""Health check HTTP server."""

import logging

from aiohttp import web

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """HTTP server for Kubernetes health checks and metrics."""

    def __init__(self, bot, port: int = 8080):
        """
        Initialize health check server.

        Args:
            bot: Bot instance
            port: HTTP port to listen on
        """
        self.bot = bot
        self.port = port
        self.app = web.Application()
        self.runner = None

        # Register routes
        self.app.router.add_get("/healthz", self.liveness)
        self.app.router.add_get("/readyz", self.readiness)
        self.app.router.add_get("/metrics", self.metrics)

    async def liveness(self, request):
        """
        Liveness probe: Is the bot process alive?

        Returns:
            200 if alive, 500 if dead
        """
        if self.bot.is_closed():
            return web.Response(status=500, text="Bot is closed")
        return web.Response(status=200, text="OK")

    async def readiness(self, request):
        """
        Readiness probe: Is the bot ready to handle traffic?

        Checks:
        - Discord connection
        - Database connection

        Returns:
            200 if ready, 503 if not ready
        """
        # Check Discord connection
        if not self.bot.is_ready():
            return web.Response(status=503, text="Discord not connected")

        # Check database connection
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return web.Response(status=503, text=f"Database error: {e}")

        return web.Response(status=200, text="Ready")

    async def metrics(self, request):
        """
        Prometheus metrics endpoint.

        Returns:
            Metrics in Prometheus text format
        """
        from bot.utils.metrics import generate_metrics_response

        # Update cache size metric before generating response
        if self.bot.cache and self.bot.metrics:
            self.bot.metrics.set_cache_size(self.bot.cache.size())

        metrics_text = generate_metrics_response()
        return web.Response(text=metrics_text.decode("utf-8"), content_type="text/plain")

    async def start(self):
        """Start health check server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"Health check server listening on port {self.port}")
