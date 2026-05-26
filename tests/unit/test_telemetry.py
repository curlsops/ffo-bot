import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import bot.utils.telemetry as telemetry_mod
from bot.handlers.messages import MessageHandler


@pytest.fixture(autouse=True)
def _isolated_tracer_provider():
    provider_store: dict[str, object] = {}

    def set_provider(provider: object) -> None:
        provider_store["provider"] = provider

    def get_provider() -> object:
        return provider_store["provider"]

    with (
        patch("bot.utils.telemetry.trace.set_tracer_provider", side_effect=set_provider),
        patch("bot.utils.telemetry.trace.get_tracer_provider", side_effect=get_provider),
        patch("opentelemetry.trace.set_tracer_provider", side_effect=set_provider),
        patch("opentelemetry.trace.get_tracer_provider", side_effect=get_provider),
    ):
        telemetry_mod._provider_configured = False
        yield
        telemetry_mod._provider_configured = False


@pytest.mark.asyncio
async def test_tracing_exports_spans_and_reconfigure_warnings(caplog):
    exporter = InMemorySpanExporter()
    with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://collector:4318"}):
        with caplog.at_level(logging.INFO):
            telemetry_mod.configure_tracing(
                enabled=True,
                service_name="unit-test",
                environment="test",
                span_exporter=exporter,
            )
        assert any(
            "Tracing enabled" in r.message and "unit-test" in r.message for r in caplog.records
        )

        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("hello"):
                ...
            with telemetry_mod.trace_span("wrapped", feature="messages"):
                ...
            with telemetry_mod.trace_span("bare"):
                ...

            bot = MagicMock()
            bot.metrics = None
            bot.phrase_matcher = None
            bot.voice_transcriber = MagicMock(enabled=False)
            bot.settings = MagicMock()
            bot.settings.feature_conversion = False
            bot.settings.feature_minecraft_whitelist = False
            bot.settings.otel_trace_discord_messages = True
            bot.is_shutting_down = MagicMock(return_value=False)
            bot._message_handler_tasks = set()

            handler = MessageHandler(bot)
            handler._handle_message = AsyncMock()

            msg = MagicMock()
            msg.author.bot = False
            msg.guild.id = 10
            msg.channel.id = 20
            msg.content = ""
            msg.attachments = []

            await handler.on_message(msg)

            trace.get_tracer_provider().force_flush()

            caplog.clear()
            with caplog.at_level(logging.WARNING):
                telemetry_mod.configure_tracing(
                    enabled=True,
                    service_name="other",
                    environment="test",
                    span_exporter=exporter,
                )
            assert any("already configured" in r.message for r in caplog.records)

            names = {s.name for s in exporter.get_finished_spans()}
            assert "hello" in names
            assert "wrapped" in names
            assert "bare" in names
            assert "discord.message" in names
            handler._handle_message.assert_awaited_once()
        finally:
            caplog.clear()
            telemetry_mod.shutdown_tracing()

    assert telemetry_mod._provider_configured is False


def test_configure_disabled_does_not_set_tracer_provider():
    with patch("bot.utils.telemetry.trace.set_tracer_provider") as mock_set:
        telemetry_mod.configure_tracing(enabled=False, service_name=None, environment="test")
        mock_set.assert_not_called()


def test_shutdown_without_prior_configure_is_safe():
    telemetry_mod.shutdown_tracing()
    assert telemetry_mod._provider_configured is False


def test_shutdown_when_global_provider_is_not_sdk():
    telemetry_mod._provider_configured = True
    try:
        with patch("bot.utils.telemetry.trace.get_tracer_provider", return_value=object()):
            telemetry_mod.shutdown_tracing()
        assert telemetry_mod._provider_configured is False
    finally:
        telemetry_mod._provider_configured = False


def test_install_asyncpg_warns_on_instrument_error(caplog):
    mock_cls = MagicMock()
    mock_cls.return_value.is_instrumented_by_opentelemetry = False
    mock_cls.return_value.instrument.side_effect = RuntimeError("instrument boom")
    with patch("opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor", mock_cls):
        with caplog.at_level(logging.WARNING):
            telemetry_mod._install_asyncpg_instrumentation()
    assert any("asyncpg trace instrumentation" in r.message for r in caplog.records)


def test_install_asyncpg_skips_when_already_instrumented():
    mock_cls = MagicMock()
    mock_cls.return_value.is_instrumented_by_opentelemetry = True
    with patch("opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor", mock_cls):
        telemetry_mod._install_asyncpg_instrumentation()
    mock_cls.return_value.instrument.assert_not_called()


def test_install_asyncpg_calls_instrument_when_needed(caplog):
    mock_cls = MagicMock()
    mock_cls.return_value.is_instrumented_by_opentelemetry = False
    with patch("opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor", mock_cls):
        with caplog.at_level(logging.DEBUG):
            telemetry_mod._install_asyncpg_instrumentation()
    mock_cls.return_value.instrument.assert_called_once()


def test_command_feature_name():
    assert telemetry_mod.command_feature_name("music play") == "music"
    assert telemetry_mod.command_feature_name("") == "unknown"


def test_span_context_fields_empty_without_span():
    assert telemetry_mod.span_context_fields() == {}


def test_logging_extra_merges_attrs():
    extra = telemetry_mod.logging_extra(guild_id=1, interaction_id=2, skip=None)
    assert extra["guild_id"] == 1
    assert extra["interaction_id"] == 2
    assert "skip" not in extra


def test_feature_debug_skips_when_disabled(caplog):
    log = logging.getLogger("test.feature_debug")
    with caplog.at_level(logging.INFO):
        telemetry_mod.feature_debug(log, "music", "hidden %s", "x", guild_id=1)
    assert not caplog.records


def test_feature_debug_logs_when_enabled(caplog):
    log = logging.getLogger("test.feature_debug")
    with caplog.at_level(logging.DEBUG):
        telemetry_mod.feature_debug(log, "music", "visible %s", "x", guild_id=1)
    assert any("visible x" in r.message for r in caplog.records)


def test_trace_context_filter_sets_empty_without_span():
    filt = telemetry_mod.TraceContextFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert record.trace_id == ""
    assert record.span_id == ""


def test_trace_span_without_feature():
    exporter = InMemorySpanExporter()
    telemetry_mod.configure_tracing(
        enabled=True,
        service_name="unit-test",
        environment="test",
        span_exporter=exporter,
    )
    try:
        with telemetry_mod.trace_span("plain"):
            ...
        trace.get_tracer_provider().force_flush()
        assert any(s.name == "plain" for s in exporter.get_finished_spans())
    finally:
        telemetry_mod.shutdown_tracing()


@pytest.mark.asyncio
async def test_trace_span_yields_active_span():
    exporter = InMemorySpanExporter()
    telemetry_mod.configure_tracing(
        enabled=True,
        service_name="unit-test",
        environment="test",
        span_exporter=exporter,
    )
    try:
        with telemetry_mod.trace_span("wrapped", feature="music") as span:
            assert span.is_recording()
        trace.get_tracer_provider().force_flush()
        assert any(s.name == "wrapped" for s in exporter.get_finished_spans())
    finally:
        telemetry_mod.shutdown_tracing()


def test_span_context_fields_with_active_span():
    exporter = InMemorySpanExporter()
    telemetry_mod.configure_tracing(
        enabled=True,
        service_name="unit-test",
        environment="test",
        span_exporter=exporter,
    )
    try:
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("ctx-span"):
            fields = telemetry_mod.span_context_fields()
        assert len(fields["trace_id"]) == 32
        assert len(fields["span_id"]) == 16
    finally:
        telemetry_mod.shutdown_tracing()


def test_configure_otlp_batch_processor(caplog):
    telemetry_mod._provider_configured = False
    with patch("bot.utils.telemetry.OTLPSpanExporter", return_value=MagicMock()):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318"}):
            with caplog.at_level(logging.DEBUG):
                telemetry_mod.configure_tracing(
                    enabled=True,
                    service_name="svc",
                    environment="prod",
                )
    assert telemetry_mod._provider_configured
    assert any("Tracing enabled" in r.message and "svc" in r.message for r in caplog.records)
    telemetry_mod.shutdown_tracing()


def test_configure_when_provider_not_applied(caplog):
    telemetry_mod._provider_configured = False
    with patch("bot.utils.telemetry.trace.set_tracer_provider"):
        with patch(
            "bot.utils.telemetry.trace.get_tracer_provider",
            return_value=object(),
        ):
            with caplog.at_level(logging.WARNING):
                telemetry_mod.configure_tracing(
                    enabled=True,
                    service_name="x",
                    environment="test",
                    span_exporter=InMemorySpanExporter(),
                )
    assert telemetry_mod._provider_configured is False
    assert any("not applied" in r.message for r in caplog.records)
