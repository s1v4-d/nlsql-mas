"""Structured logging configuration with structlog for production observability."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog
from structlog.types import Processor

if TYPE_CHECKING:
    from retail_insights.core.config import Settings


def add_opentelemetry_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add OpenTelemetry trace context to log entries for correlation."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span.is_recording():
            ctx = span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass
    except Exception:
        pass
    return event_dict


def add_service_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add service metadata to all log entries."""
    event_dict.setdefault("service", "retail-insights")
    return event_dict


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structlog for production use with FastAPI.

    Args:
        settings: Application settings. If None, uses defaults.
    """
    if settings is None:
        from retail_insights.core.config import get_settings

        settings = get_settings()

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    is_development = settings.ENVIRONMENT == "development"
    is_tty = sys.stderr.isatty()

    common_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        add_opentelemetry_context,
        add_service_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_development and is_tty:
        processors = [
            *common_processors,
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        log_factory = structlog.PrintLoggerFactory()
    else:
        processors = [
            *common_processors,
            structlog.processors.format_exc_info,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
        log_factory = structlog.WriteLoggerFactory()

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=log_factory,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger.

    Args:
        name: Logger name. If None, uses caller's module name.

    Returns:
        Configured bound logger with context support.
    """
    return structlog.get_logger(name)
