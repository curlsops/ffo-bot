import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from bot.utils.telemetry import TraceContextFilter
from config.logging_config import setup_logging


class TestSetupLogging:
    def test_json_format(self):
        root = setup_logging(log_level="DEBUG", log_format="json")
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert "Json" in root.handlers[0].formatter.__class__.__name__
        assert any(isinstance(f, TraceContextFilter) for f in root.handlers[0].filters)

    def test_text_format(self):
        root = setup_logging(log_level="INFO", log_format="text")
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert "Formatter" in root.handlers[0].formatter.__class__.__name__

    def test_case_insensitive_level(self):
        root = setup_logging(log_level="debug", log_format="json")
        assert root.level == logging.DEBUG

    def test_warning_level(self):
        root = setup_logging(log_level="WARNING", log_format="json")
        assert root.level == logging.WARNING

    def test_error_level(self):
        root = setup_logging(log_level="ERROR", log_format="text")
        assert root.level == logging.ERROR

    def test_critical_level(self):
        root = setup_logging(log_level="CRITICAL", log_format="json")
        assert root.level == logging.CRITICAL

    def test_debug_enables_third_party_loggers(self):
        setup_logging(log_level="DEBUG", log_format="json")
        assert logging.getLogger("bot").level == logging.DEBUG
        assert logging.getLogger("mafic").level == logging.DEBUG
        assert logging.getLogger("mafic.node").level == logging.DEBUG
        assert logging.getLogger("discord.http").level == logging.DEBUG
        assert logging.getLogger("discord.voice_state").level == logging.DEBUG
        assert logging.getLogger("asyncpg").level == logging.INFO

    def test_debug_verbose_third_party_can_be_disabled(self):
        setup_logging(log_level="DEBUG", log_format="json", log_verbose_third_party=False)
        assert logging.getLogger("bot").level == logging.DEBUG
        assert logging.getLogger("mafic").level == logging.WARNING

    def test_otel_sdk_loggers_when_tracing_enabled(self):
        setup_logging(log_level="INFO", log_format="json", otel_tracing_enabled=True)
        assert logging.getLogger("opentelemetry.sdk.trace").level == logging.DEBUG

    def test_info_quietens_third_party_loggers(self):
        setup_logging(log_level="INFO", log_format="json")
        assert logging.getLogger("discord").level == logging.INFO
        assert logging.getLogger("mafic").level == logging.WARNING
        assert logging.getLogger("aiohttp").level == logging.WARNING


class TestTraceContextFilter:
    def test_injects_trace_and_span_ids_when_span_active(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        previous = trace.get_tracer_provider()
        trace.set_tracer_provider(provider)
        try:
            filt = TraceContextFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="msg",
                args=(),
                exc_info=None,
            )
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("span-a"):
                assert filt.filter(record) is True
            assert len(record.trace_id) == 32
            assert len(record.span_id) == 16
        finally:
            trace.set_tracer_provider(previous)

    def test_empty_ids_without_active_span(self):
        filt = TraceContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        assert filt.filter(record) is True
        assert record.trace_id == ""
        assert record.span_id == ""

    def test_trace_ids_appear_in_json_log_output(self, capsys):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        previous = trace.get_tracer_provider()
        trace.set_tracer_provider(provider)
        try:
            setup_logging(log_level="DEBUG", log_format="json")
            log = logging.getLogger("test.logging_config")
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("correlated"):
                log.info("correlated message")
            out = capsys.readouterr().out
            assert "correlated message" in out
            assert '"trace_id":' in out
            assert '"span_id":' in out
        finally:
            trace.set_tracer_provider(previous)
