import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import bot.utils.telemetry as telemetry_mod
from bot.handlers.messages import MessageHandler


def test_configure_disabled_does_not_set_tracer_provider():
    with patch("bot.utils.telemetry.trace.set_tracer_provider") as mock_set:
        telemetry_mod.configure_tracing(enabled=False, service_name=None, environment="test")
        mock_set.assert_not_called()


def test_shutdown_without_prior_configure_is_safe():
    telemetry_mod.shutdown_tracing()


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


def test_install_asyncpg_calls_instrument_when_needed():
    mock_cls = MagicMock()
    mock_cls.return_value.is_instrumented_by_opentelemetry = False
    with patch("opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor", mock_cls):
        telemetry_mod._install_asyncpg_instrumentation()
    mock_cls.return_value.instrument.assert_called_once()


@pytest.mark.asyncio
async def test_tracing_exports_spans_and_reconfigure_warnings(caplog):
    exporter = InMemorySpanExporter()
    telemetry_mod.configure_tracing(
        enabled=True,
        service_name="unit-test",
        environment="test",
        span_exporter=exporter,
    )

    try:
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("hello"):
            pass

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
        assert "discord.message" in names
        handler._handle_message.assert_awaited_once()
    finally:
        telemetry_mod.shutdown_tracing()

    assert telemetry_mod._provider_configured is False
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        telemetry_mod.configure_tracing(
            enabled=True,
            service_name="after_shutdown",
            environment="test",
            span_exporter=InMemorySpanExporter(),
        )
    assert any("global provider already set" in r.message for r in caplog.records)
