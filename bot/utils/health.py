import logging

from aiohttp import web

from bot.utils.metrics import generate_metrics_response

logger = logging.getLogger(__name__)


class HealthCheckServer:
    def __init__(self, bot, port: int = 8080):
        self.bot = bot
        self.port = port
        self.app = web.Application()
        self.runner = None
        self.app.router.add_get("/healthz", self.liveness)
        self.app.router.add_get("/readyz", self.readiness)
        self.app.router.add_get("/metrics", self.metrics)

    async def liveness(self, request):
        if self.bot.is_closed():
            return web.Response(status=500, text="Bot is closed")
        return web.Response(status=200, text="OK")

    async def readiness(self, request):
        if not self.bot.is_ready():
            return web.Response(status=503, text="Discord not connected")
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            return web.Response(status=503, text=f"Database error: {e}")
        return web.Response(status=200, text="Ready")

    async def metrics(self, request):
        if self.bot.cache and self.bot.metrics:
            self.bot.metrics.set_cache_size(self.bot.cache.size())
        return web.Response(
            text=generate_metrics_response().decode("utf-8"), content_type="text/plain"
        )

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        await web.TCPSite(self.runner, "0.0.0.0", self.port).start()
