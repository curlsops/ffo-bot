import logging
from unittest.mock import MagicMock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from bot.utils import log_context


def test_trace_fields_for_log_delegates_to_span_context():
    assert log_context.trace_fields_for_log() == {}


def test_log_debug_skips_when_not_enabled(caplog):
    log = logging.getLogger("test.log_context")
    with caplog.at_level(logging.INFO):
        log_context.log_debug(log, "skip %s", "x", feature="faq")
    assert not caplog.records


def test_log_debug_emits_with_extra(caplog):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    previous = trace.get_tracer_provider()
    trace.set_tracer_provider(provider)
    try:
        log = logging.getLogger("test.log_context.debug")
        log.setLevel(logging.DEBUG)
        with trace.get_tracer("t").start_as_current_span("s"):
            with caplog.at_level(logging.DEBUG):
                log_context.log_debug(log, "detail %s", "ok", feature="music")
        assert caplog.records[-1].feature == "music"
        assert len(caplog.records[-1].trace_id) == 32
    finally:
        trace.set_tracer_provider(previous)


def test_interaction_log_fields():
    user = MagicMock(id=99)
    interaction = MagicMock(guild_id=1, user=user, id=2, channel_id=3)
    fields = log_context.interaction_log_fields(interaction)
    assert fields == {
        "guild_id": 1,
        "user_id": 99,
        "interaction_id": 2,
        "channel_id": 3,
    }


def test_log_command_start_info_and_feature_debug(caplog):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    previous = trace.get_tracer_provider()
    trace.set_tracer_provider(provider)
    try:
        log = logging.getLogger("test.log_context.cmd")
        log.setLevel(logging.DEBUG)
        interaction = MagicMock(guild_id=10, user=MagicMock(id=20), id=30, channel_id=40)
        with caplog.at_level(logging.DEBUG):
            log_context.log_command_start(log, "faq", "faq list", interaction)
        assert any("faq list start" in r.message for r in caplog.records)
        assert any(
            r.levelno == logging.DEBUG and "deferred" in r.getMessage() for r in caplog.records
        )
    finally:
        trace.set_tracer_provider(previous)
