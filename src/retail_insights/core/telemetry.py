"""OpenTelemetry configuration for distributed tracing and metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

    from retail_insights.core.config import Settings


def configure_telemetry(app: FastAPI, settings: Settings | None = None) -> None:
    """Configure OpenTelemetry for distributed tracing.

    Args:
        app: FastAPI application to instrument.
        settings: Application settings. If None, uses defaults.
    """
    if settings is None:
        from retail_insights.core.config import get_settings

        settings = get_settings()

    if not settings.OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

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

    except ImportError as e:
        import structlog

        logger = structlog.get_logger(__name__)
        logger.warning("opentelemetry_not_available", error=str(e))


def _configure_exporters(provider: Any, settings: Any) -> None:
    """Configure trace exporters based on settings."""
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    exporter_type = settings.OTEL_EXPORTER_TYPE.lower()

    if exporter_type == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            pass

    elif exporter_type == "xray":
        try:
            from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator

            provider._id_generator = AwsXRayIdGenerator()

            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            pass

    elif exporter_type == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))


def get_tracer(name: str) -> Any:
    """Get an OpenTelemetry tracer for manual instrumentation.

    Args:
        name: Tracer name (typically __name__).

    Returns:
        OpenTelemetry tracer instance.
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:

        class NoOpTracer:
            def start_as_current_span(self, name: str, **kwargs: Any) -> Any:
                from contextlib import nullcontext

                return nullcontext()

        return NoOpTracer()


def create_span(name: str, attributes: dict[str, Any] | None = None) -> Any:
    """Create a new span for tracing.

    Args:
        name: Span name.
        attributes: Optional span attributes.

    Returns:
        Context manager for the span.
    """
    tracer = get_tracer("retail_insights")
    return tracer.start_as_current_span(name, attributes=attributes or {})
