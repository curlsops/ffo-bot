"""Tests for health check server functionality."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.utils.health import HealthCheckServer


class TestHealthCheckServerInit:
    """Tests for HealthCheckServer initialization."""

    def test_health_server_initialization(self):
        """Test HealthCheckServer initialization."""
        mock_bot = MagicMock()

        server = HealthCheckServer(mock_bot, port=8080)

        assert server.bot == mock_bot
        assert server.port == 8080
        assert server.app is not None
        assert server.runner is None

    def test_health_server_default_port(self):
        """Test HealthCheckServer with default port."""
        mock_bot = MagicMock()

        server = HealthCheckServer(mock_bot)

        assert server.port == 8080

    def test_health_server_routes_registered(self):
        """Test that routes are registered."""
        mock_bot = MagicMock()

        server = HealthCheckServer(mock_bot)

        routes = [r.resource.canonical for r in server.app.router.routes()]
        assert "/healthz" in routes
        assert "/readyz" in routes
        assert "/metrics" in routes


class TestHealthCheckServerLiveness:
    """Tests for liveness probe."""

    @pytest.mark.asyncio
    async def test_liveness_when_bot_alive(self):
        """Test liveness returns 200 when bot is alive."""
        mock_bot = MagicMock()
        mock_bot.is_closed.return_value = False

        server = HealthCheckServer(mock_bot)
        mock_request = MagicMock()

        response = await server.liveness(mock_request)

        assert response.status == 200
        assert response.text == "OK"

    @pytest.mark.asyncio
    async def test_liveness_when_bot_closed(self):
        """Test liveness returns 500 when bot is closed."""
        mock_bot = MagicMock()
        mock_bot.is_closed.return_value = True

        server = HealthCheckServer(mock_bot)
        mock_request = MagicMock()

        response = await server.liveness(mock_request)

        assert response.status == 500
        assert "closed" in response.text.lower()


class TestHealthCheckServerReadiness:
    """Tests for readiness probe."""

    @pytest.mark.asyncio
    async def test_readiness_when_not_ready(self):
        """Test readiness returns 503 when not ready."""
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = False

        server = HealthCheckServer(mock_bot)
        mock_request = MagicMock()

        response = await server.readiness(mock_request)

        assert response.status == 503
        assert "not connected" in response.text.lower()

    @pytest.mark.asyncio
    async def test_readiness_when_db_fails(self):
        """Test readiness returns 503 when database fails."""
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True

        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = Exception("Connection failed")

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_bot.db_pool = MagicMock()
        mock_bot.db_pool.acquire = acquire

        server = HealthCheckServer(mock_bot)
        mock_request = MagicMock()

        response = await server.readiness(mock_request)

        assert response.status == 503
        assert "database" in response.text.lower()

    @pytest.mark.asyncio
    async def test_readiness_when_healthy(self):
        """Test readiness returns 200 when healthy."""
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True

        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 1

        @asynccontextmanager
        async def acquire():
            yield mock_conn

        mock_bot.db_pool = MagicMock()
        mock_bot.db_pool.acquire = acquire

        server = HealthCheckServer(mock_bot)
        mock_request = MagicMock()

        response = await server.readiness(mock_request)

        assert response.status == 200
        assert response.text == "Ready"


class TestHealthCheckServerMetrics:
    """Tests for metrics endpoint."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self):
        """Test metrics endpoint returns prometheus data."""
        mock_bot = MagicMock()
        mock_bot.cache = MagicMock()
        mock_bot.cache.size.return_value = 100
        mock_bot.metrics = MagicMock()

        server = HealthCheckServer(mock_bot)
        mock_request = MagicMock()

        with patch("bot.utils.metrics.generate_latest") as mock_gen:
            mock_gen.return_value = b"# HELP test_metric\ntest_metric 1.0\n"

            response = await server.metrics(mock_request)

            assert response.status == 200
            assert response.content_type == "text/plain"
            mock_bot.metrics.set_cache_size.assert_called_with(100)

    @pytest.mark.asyncio
    async def test_metrics_without_cache(self):
        """Test metrics endpoint without cache."""
        mock_bot = MagicMock()
        mock_bot.cache = None
        mock_bot.metrics = MagicMock()

        server = HealthCheckServer(mock_bot)
        mock_request = MagicMock()

        with patch("bot.utils.metrics.generate_latest") as mock_gen:
            mock_gen.return_value = b"# HELP test_metric\ntest_metric 1.0\n"

            response = await server.metrics(mock_request)

            assert response.status == 200
            mock_bot.metrics.set_cache_size.assert_not_called()


class TestHealthCheckServerStart:
    """Tests for server start."""

    @pytest.mark.asyncio
    async def test_start_server(self):
        """Test starting the health check server."""
        mock_bot = MagicMock()

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
                mock_site.start.assert_called_once()
                assert server.runner == mock_runner
