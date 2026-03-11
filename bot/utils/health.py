import json
import logging
import time

import nacl.encoding
import nacl.exceptions
import nacl.signing
from aiohttp import web

from bot.utils.metrics import generate_metrics_response

logger = logging.getLogger(__name__)


def _verify_discord_signature(
    body: bytes, signature: str, timestamp: str, public_key_hex: str
) -> bool:
    try:
        verify_key = nacl.signing.VerifyKey(
            public_key_hex.encode(), encoder=nacl.encoding.HexEncoder
        )
        message = timestamp.encode() + body
        sig_bytes = bytes.fromhex(signature)
        verify_key.verify(message, sig_bytes)
        return True
    except (nacl.exceptions.BadSignatureError, ValueError):
        return False


class HealthCheckServer:
    CACHE_SIZE_UPDATE_INTERVAL = 5.0

    def __init__(
        self,
        bot,
        port: int = 8080,
        public_key: str | None = None,
        host: str = "0.0.0.0",
    ):
        self.bot = bot
        self.port = port
        self.public_key = public_key
        self.host = host
        self._last_cache_size: int | None = None
        self._last_cache_size_ts: float | None = None
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
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
        if not self.bot.db_pool:
            return web.Response(status=503, text="Database not initialized")
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            logger.warning("readiness check failed: %s", e)
            return web.Response(status=503, text="Database unavailable")
        return web.Response(status=200, text="Ready")

    async def metrics(self, request):
        if self.bot.cache and self.bot.metrics:
            now = time.monotonic()
            if (
                self._last_cache_size_ts is None
                or now - self._last_cache_size_ts >= self.CACHE_SIZE_UPDATE_INTERVAL
            ):
                try:
                    self._last_cache_size = self.bot.cache.size()
                except Exception as e:
                    logger.warning("Failed to compute cache size for metrics: %s", e)
                self._last_cache_size_ts = now
            if self._last_cache_size is not None:
                self.bot.metrics.set_cache_size(self._last_cache_size)
        return web.Response(
            text=generate_metrics_response().decode("utf-8"), content_type="text/plain"
        )

    async def interactions(self, request: web.Request) -> web.Response:
        if request.method != "POST":
            return web.Response(status=405)
        if not self.public_key:
            return web.Response(status=501, text="Interactions endpoint not configured")
        signature = request.headers.get("X-Signature-Ed25519")
        timestamp = request.headers.get("X-Signature-Timestamp")
        if not signature or not timestamp:
            return web.Response(status=401, text="Missing signature headers")
        body = await request.read()
        if not _verify_discord_signature(body, signature, timestamp, self.public_key):
            return web.Response(status=401, text="Invalid request signature")
        try:
            body_text = body.decode("utf-8")
        except UnicodeDecodeError:
            return web.Response(status=400, text="Invalid encoding")
        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")
        if data.get("type") == 1:
            return web.json_response({"type": 1})
        return web.Response(status=501, text="Interaction types beyond PING not yet supported")

    async def start(self):
        if self.public_key:
            self.app.router.add_post("/interactions", self.interactions)
        runner = web.AppRunner(self.app)
        self.runner = runner
        await runner.setup()
        await web.TCPSite(runner, self.host, self.port).start()
