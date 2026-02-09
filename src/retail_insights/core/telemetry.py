"""OpenTelemetry configuration for distributed tracing and metrics."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from retail_insights.core.config import Settings, get_settings


def configure_telemetry(app: FastAPI, settings: Settings | None = None) -> None:
    """Configure OpenTelemetry for distributed tracing."""
    if settings is None:
        settings = get_settings()

    if not settings.OTEL_ENABLED:
        return

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": "1.0.0",
            "deployment.environment": settings.ENVIRONMENT,
        }
    )

    provider = TracerProvider(resource=resource)
    _configure_exporters(provider, settings)
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,ready,metrics,favicon.ico",
        tracer_provider=provider,
    )


def _configure_exporters(provider: TracerProvider, settings: Settings) -> None:
    """Configure trace exporters based on settings."""
    exporter_type = settings.OTEL_EXPORTER_TYPE.lower()

    if exporter_type == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    elif exporter_type == "xray":
        try:
            from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator

            provider._id_generator = AwsXRayIdGenerator()
        except ImportError:
            pass  # AWS extension not installed

        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    elif exporter_type == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))


def get_tracer(name: str) -> trace.Tracer:
    """Get an OpenTelemetry tracer for manual instrumentation."""
    return trace.get_tracer(name)


def create_span(name: str, attributes: dict[str, Any] | None = None) -> Any:
    """Create a new span for tracing."""
    tracer = get_tracer("retail_insights")
    return tracer.start_as_current_span(name, attributes=attributes or {})
