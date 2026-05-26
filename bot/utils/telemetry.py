from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import Span

logger = logging.getLogger(__name__)

_provider_configured = False

_ATTR = str | int | bool | float


def command_feature_name(qualified_name: str) -> str:
    if not qualified_name:
        return "unknown"
    return qualified_name.split()[0]


def span_context_fields() -> dict[str, str]:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return {}
    return {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
    }


def logging_extra(**attrs: _ATTR) -> dict[str, Any]:
    extra: dict[str, Any] = dict(span_context_fields())
    for key, value in attrs.items():
        if value is not None:
            extra[key] = value
    return extra


def feature_debug(
    log: logging.Logger,
    feature: str,
    msg: str,
    *args: object,
    **attrs: _ATTR,
) -> None:
    if not log.isEnabledFor(logging.DEBUG):
        return
    log.debug(msg, *args, extra=logging_extra(feature=feature, **attrs))


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        fields = span_context_fields()
        record.trace_id = fields.get("trace_id", "")
        record.span_id = fields.get("span_id", "")
        return True


@contextmanager
def trace_span(
    name: str,
    *,
    feature: str | None = None,
    attributes: dict[str, _ATTR] | None = None,
) -> Iterator[Span]:
    attrs: dict[str, _ATTR] = dict(attributes or {})
    if feature:
        attrs["ffo.feature"] = feature
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name, attributes=attrs) as span:
        yield span


def _otlp_traces_endpoint() -> str:
    return os.environ.get(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
    )


def _install_asyncpg_instrumentation() -> None:
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        instr = AsyncPGInstrumentor()
        if not instr.is_instrumented_by_opentelemetry:
            logger.debug("Installing asyncpg OpenTelemetry instrumentation")
            instr.instrument()
        else:
            logger.debug("asyncpg already instrumented for OpenTelemetry")
    except Exception as e:
        logger.warning("asyncpg trace instrumentation failed: %s", e)


def configure_tracing(
    *,
    enabled: bool,
    service_name: str | None,
    environment: str,
    span_exporter: SpanExporter | None = None,
) -> None:
    global _provider_configured
    if not enabled:
        logger.debug("OpenTelemetry tracing disabled (OTEL_TRACING_ENABLED=false)")
        return
    if _provider_configured:
        logger.warning("Tracing already configured; skipping duplicate init")
        return

    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "ffo-bot")
    endpoint = _otlp_traces_endpoint()
    processor_name = "SimpleSpanProcessor" if span_exporter is not None else "BatchSpanProcessor"
    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAME: name,
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: environment,
        }
    )
    provider = SDKTracerProvider(resource=resource)
    exporter = span_exporter if span_exporter is not None else OTLPSpanExporter()
    processor = (
        SimpleSpanProcessor(exporter) if span_exporter is not None else BatchSpanProcessor(exporter)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    if trace.get_tracer_provider() is not provider:
        logger.warning("Tracer provider not applied (global provider already set)")
        return

    _provider_configured = True

    _install_asyncpg_instrumentation()

    logger.info(
        "Tracing enabled service=%s environment=%s endpoint=%s processor=%s",
        name,
        environment,
        endpoint,
        processor_name,
    )
    logger.debug("Tracing exporter=%s", type(exporter).__name__)


def shutdown_tracing() -> None:
    global _provider_configured
    if not _provider_configured:
        logger.debug("Tracing shutdown skipped (not configured)")
        return
    current = trace.get_tracer_provider()
    if isinstance(current, SDKTracerProvider):
        logger.debug("Shutting down OpenTelemetry tracer provider")
        current.shutdown()
    _provider_configured = False
    logger.info("Tracing shutdown complete")
