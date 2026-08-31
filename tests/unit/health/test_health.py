from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.health import HealthCheckServer, _verify_discord_signature


@pytest.fixture
def mock_bot():
    return MagicMock()


@pytest.fixture
def server(mock_bot):
    return HealthCheckServer(mock_bot, port=8080)


@asynccontextmanager
async def _db_ctx(conn):
    yield conn


def test_verify_discord_signature_invalid():
    assert _verify_discord_signature(b"body", "bad", "ts", "0" * 64) is False


def test_verify_discord_signature_valid():
    with patch("bot.utils.health.nacl.signing.VerifyKey") as mock_vk:
        mock_vk.return_value.verify = MagicMock()
        assert _verify_discord_signature(b"body", "00" * 32, "ts", "0" * 64) is True


class TestHealthCheckServerInit:
    def test_initialization(self, server, mock_bot):
        assert server.bot == mock_bot
        assert server.port == 8080
        assert server.runner is None

    def test_default_port(self, mock_bot):
        assert HealthCheckServer(mock_bot).port == 8080

    def test_routes_registered(self, server):
        routes = [r.resource.canonical for r in server.app.router.routes()]
        assert "/healthz" in routes and "/readyz" in routes and "/metrics" in routes


class TestLiveness:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("is_closed,expected_status", [(False, 200), (True, 500)])
    async def test_liveness(self, server, is_closed, expected_status):
        server.bot.is_closed.return_value = is_closed
        response = await server.liveness(MagicMock())
        assert response.status == expected_status


class TestReadiness:
    @pytest.mark.asyncio
    async def test_not_ready(self, server):
        server.bot.is_ready.return_value = False
        response = await server.readiness(MagicMock())
        assert response.status == 503 and "not connected" in response.text.lower()

    @pytest.mark.asyncio
    async def test_db_pool_none(self, server):
        server.bot.is_ready.return_value = True
        server.bot.db_pool = None
        response = await server.readiness(MagicMock())
        assert response.status == 503 and "database" in response.text.lower()

    @pytest.mark.asyncio
    async def test_db_fails(self, server):
        server.bot.is_ready.return_value = True
        conn = AsyncMock(fetchval=AsyncMock(side_effect=Exception("Connection failed")))
        server.bot.db_pool = MagicMock(acquire=lambda: _db_ctx(conn))
        response = await server.readiness(MagicMock())
        assert response.status == 503 and "database" in response.text.lower()

    @pytest.mark.asyncio
    async def test_healthy(self, server):
        server.bot.is_ready.return_value = True
        conn = AsyncMock(fetchval=AsyncMock(return_value=1))
        server.bot.db_pool = MagicMock(acquire=lambda: _db_ctx(conn))
        response = await server.readiness(MagicMock())
        assert response.status == 200 and response.text == "Ready"


class TestMetrics:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("has_cache", [True, False])
    async def test_metrics_endpoint(self, server, has_cache):
        server.bot.cache = MagicMock(size=MagicMock(return_value=100)) if has_cache else None
        server.bot.metrics = MagicMock()

        with patch("bot.utils.metrics.generate_latest", return_value=b"test_metric 1.0\n"):
            response = await server.metrics(MagicMock())
            assert response.status == 200 and response.content_type == "text/plain"
            if has_cache:
                server.bot.metrics.set_cache_size.assert_called_with(100)
            else:
                server.bot.metrics.set_cache_size.assert_not_called()

    @pytest.mark.asyncio
    async def test_metrics_when_bot_metrics_none(self, server):
        server.bot.cache = None
        server.bot.metrics = None
        with patch("bot.utils.metrics.generate_metrics_response", return_value=b"# metrics\n"):
            response = await server.metrics(MagicMock())
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_metrics_cache_size_exception_logged(self, server):
        server.bot.cache = MagicMock(size=MagicMock(side_effect=RuntimeError("cache error")))
        server.bot.metrics = MagicMock()
        with patch("bot.utils.metrics.generate_metrics_response", return_value=b"# metrics\n"):
            response = await server.metrics(MagicMock())
        assert response.status == 200
        server.bot.metrics.set_cache_size.assert_not_called()

    @pytest.mark.asyncio
    async def test_metrics_cache_size_throttled(self, server):
        server.bot.cache = MagicMock(size=MagicMock(return_value=10))
        server.bot.metrics = MagicMock()
        with patch("bot.utils.metrics.generate_metrics_response", return_value=b"# metrics\n"):
            await server.metrics(MagicMock())
            await server.metrics(MagicMock())
        server.bot.cache.size.assert_called_once()


class TestHealthViaTestServer:
    @pytest.mark.asyncio
    async def test_healthz_200_via_http(self):
        from aiohttp.test_utils import TestClient, TestServer

        bot = MagicMock()
        bot.is_closed.return_value = False
        server = HealthCheckServer(bot)
        async with TestServer(server.app) as srv:
            async with TestClient(srv) as client:
                resp = await client.get("/healthz")
                assert resp.status == 200
                assert await resp.text() == "OK"


class TestStart:
    @pytest.mark.asyncio
    async def test_start_server(self, mock_bot):
        server = HealthCheckServer(mock_bot, port=9999)

        with patch("aiohttp.web.AppRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner
            with patch("aiohttp.web.TCPSite") as mock_site_class:
                mock_site = AsyncMock()
                mock_site_class.return_value = mock_site
                await server.start()

                mock_runner.setup.assert_called_once()
                mock_site_class.assert_called_with(mock_runner, "0.0.0.0", 9999)

    @pytest.mark.asyncio
    async def test_start_server_custom_host(self, mock_bot):
        server = HealthCheckServer(mock_bot, port=9999, host="127.0.0.1")
        with patch("aiohttp.web.AppRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner
            with patch("aiohttp.web.TCPSite") as mock_site_class:
                mock_site = AsyncMock()
                mock_site_class.return_value = mock_site
                await server.start()
                mock_site_class.assert_called_with(mock_runner, "127.0.0.1", 9999)
                assert server.runner == mock_runner

    @pytest.mark.asyncio
    async def test_start_with_public_key_adds_interactions_route(self, mock_bot):
        server = HealthCheckServer(mock_bot, port=9999, public_key="0" * 64)
        with patch("aiohttp.web.AppRunner") as mock_runner_class:
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner
            with patch("aiohttp.web.TCPSite") as mock_site_class:
                mock_site = AsyncMock()
                mock_site_class.return_value = mock_site
                await server.start()
        routes = [r.resource.canonical for r in server.app.router.routes()]
        assert "/interactions" in routes

    @pytest.mark.parametrize("port", [8080, 3000, 9999])
    def test_server_port(self, mock_bot, port):
        server = HealthCheckServer(mock_bot, port=port)
        assert server.port == port


class TestInteractions:
    @pytest.mark.asyncio
    async def test_interactions_get_405(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key="0" * 64)
        req = MagicMock()
        req.method = "GET"
        resp = await server.interactions(req)
        assert resp.status == 405

    @pytest.mark.asyncio
    async def test_interactions_no_public_key_501(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key=None)
        req = MagicMock()
        req.method = "POST"
        req.headers = {}
        req.read = AsyncMock(return_value=b"{}")
        resp = await server.interactions(req)
        assert resp.status == 501

    @pytest.mark.asyncio
    async def test_interactions_missing_headers_401(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key="0" * 64)
        req = MagicMock()
        req.method = "POST"
        req.headers = {}
        req.read = AsyncMock(return_value=b"{}")
        resp = await server.interactions(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_interactions_invalid_signature_401(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key="0" * 64)
        req = MagicMock()
        req.method = "POST"
        req.headers = {
            "X-Signature-Ed25519": "bad",
            "X-Signature-Timestamp": "123",
        }
        req.read = AsyncMock(return_value=b"{}")
        resp = await server.interactions(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_interactions_invalid_encoding_400(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key="0" * 64)
        req = MagicMock()
        req.method = "POST"
        req.headers = {
            "X-Signature-Ed25519": "0" * 128,
            "X-Signature-Timestamp": "123",
        }
        req.read = AsyncMock(return_value=b"\xff\xfe")
        with patch("bot.utils.health._verify_discord_signature", return_value=True):
            resp = await server.interactions(req)
        assert resp.status == 400 and "encoding" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_interactions_invalid_json_400(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key="0" * 64)
        req = MagicMock()
        req.method = "POST"
        req.headers = {
            "X-Signature-Ed25519": "0" * 128,
            "X-Signature-Timestamp": "123",
        }
        req.read = AsyncMock(return_value=b"not json")
        with patch("bot.utils.health._verify_discord_signature", return_value=True):
            resp = await server.interactions(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_interactions_ping_returns_pong(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key="0" * 64)
        req = MagicMock()
        req.method = "POST"
        req.headers = {
            "X-Signature-Ed25519": "0" * 128,
            "X-Signature-Timestamp": "123",
        }
        req.read = AsyncMock(return_value=b'{"type": 1}')
        with patch("bot.utils.health._verify_discord_signature", return_value=True):
            resp = await server.interactions(req)
        assert resp.status == 200
        assert b'"type": 1' in resp.body

    @pytest.mark.asyncio
    async def test_interactions_unsupported_type_501(self):
        server = HealthCheckServer(MagicMock(), port=8080, public_key="0" * 64)
        req = MagicMock()
        req.method = "POST"
        req.headers = {
            "X-Signature-Ed25519": "0" * 128,
            "X-Signature-Timestamp": "123",
        }
        req.read = AsyncMock(return_value=b'{"type": 2}')
        with patch("bot.utils.health._verify_discord_signature", return_value=True):
            resp = await server.interactions(req)
        assert resp.status == 501
