import pytest

from bot.utils.metrics import BotMetrics, generate_metrics_response


@pytest.fixture(scope="module")
def metrics():
    return BotMetrics()


class TestBotMetricsInit:
    def test_metrics_initialization(self, metrics):
        assert metrics.messages_processed is not None
        assert metrics.phrase_matches is not None
        assert metrics.commands_executed is not None
        assert metrics.command_duration is not None
        assert metrics.media_downloads is not None
        assert metrics.media_download_duration is not None
        assert metrics.db_query_duration is not None
        assert metrics.db_connection_errors is not None
        assert metrics.active_connections is not None
        assert metrics.guild_count is not None
        assert metrics.cache_size is not None
        assert metrics.cache_hits is not None
        assert metrics.cache_misses is not None
        assert metrics.errors_total is not None


class TestBotMetricsMethods:
    def test_set_connection_status(self, metrics):
        metrics.set_connection_status(1)

    def test_set_connection_status_disconnected(self, metrics):
        metrics.set_connection_status(0)

    def test_set_guild_count(self, metrics):
        metrics.set_guild_count(10)

    def test_set_guild_count_zero(self, metrics):
        metrics.set_guild_count(0)

    def test_set_cache_size(self, metrics):
        metrics.set_cache_size(500)

    def test_set_cache_size_large(self, metrics):
        metrics.set_cache_size(100000)


class TestBotMetricsCounters:
    def test_messages_processed_counter(self, metrics):
        metrics.messages_processed.labels(server_id="123").inc()

    def test_phrase_matches_counter(self, metrics):
        metrics.phrase_matches.labels(server_id="123", phrase_id="456").inc()

    def test_commands_executed_counter(self, metrics):
        metrics.commands_executed.labels(
            command_name="test", server_id="123", status="success"
        ).inc()

    def test_media_downloads_counter(self, metrics):
        metrics.media_downloads.labels(server_id="123", file_type="image", status="success").inc()

    def test_db_connection_errors_counter(self, metrics):
        metrics.db_connection_errors.inc()

    def test_cache_hits_counter(self, metrics):
        metrics.cache_hits.inc()

    def test_cache_misses_counter(self, metrics):
        metrics.cache_misses.inc()

    def test_errors_total_counter(self, metrics):
        metrics.errors_total.labels(error_type="connection").inc()


class TestBotMetricsHistograms:
    def test_command_duration_histogram(self, metrics):
        metrics.command_duration.labels(command_name="test").observe(0.5)

    def test_media_download_duration_histogram(self, metrics):
        metrics.media_download_duration.labels(file_type="image").observe(2.5)

    def test_db_query_duration_histogram(self, metrics):
        metrics.db_query_duration.labels(query_type="select").observe(0.01)


class TestGenerateMetricsResponse:
    def test_generate_metrics_response(self, metrics):
        response = generate_metrics_response()
        assert isinstance(response, bytes)

    def test_generate_metrics_response_contains_data(self, metrics):
        metrics.set_guild_count(5)
        response = generate_metrics_response()
        assert isinstance(response, bytes)
        assert len(response) > 0
