from __future__ import annotations

import logging
import os

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

logger = logging.getLogger(__name__)

_provider_configured = False


def _install_asyncpg_instrumentation() -> None:
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        instr = AsyncPGInstrumentor()
        if not instr.is_instrumented_by_opentelemetry:
            instr.instrument()
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
        return
    if _provider_configured:
        logger.warning("Tracing already configured; skipping duplicate init")
        return

    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "ffo-bot")
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

    logger.info("Tracing enabled (service=%s)", name)


def shutdown_tracing() -> None:
    global _provider_configured
    if not _provider_configured:
        return
    current = trace.get_tracer_provider()
    if isinstance(current, SDKTracerProvider):
        current.shutdown()
    _provider_configured = False
