"""Tests for logging configuration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from retail_insights.core.logging import (
    add_opentelemetry_context,
    add_service_context,
    configure_logging,
    get_logger,
)


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_production(self) -> None:
        """Production mode should use JSON renderer."""
        settings = MagicMock()
        settings.ENVIRONMENT = "production"
        settings.LOG_LEVEL = "INFO"

        configure_logging(settings)

        logger = get_logger("test")
        assert logger is not None

    def test_configure_logging_development(self) -> None:
        """Development mode should use console renderer."""
        settings = MagicMock()
        settings.ENVIRONMENT = "development"
        settings.LOG_LEVEL = "DEBUG"

        configure_logging(settings)

        logger = get_logger("test.dev")
        assert logger is not None


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_bound_logger(self) -> None:
        """Should return a structlog BoundLogger."""
        logger = get_logger("test.module")
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "error")

    def test_get_logger_with_different_names(self) -> None:
        """Should return loggers for different module names."""
        logger1 = get_logger("module.one")
        logger2 = get_logger("module.two")
        assert logger1 is not None
        assert logger2 is not None


class TestAddOpenTelemetryContext:
    """Tests for add_opentelemetry_context processor."""

    def test_returns_event_dict_without_span(self) -> None:
        """Should return event dict even without active span."""
        event_dict = {"event": "test", "key": "value"}
        result = add_opentelemetry_context(None, "info", event_dict)

        assert result["event"] == "test"
        assert result["key"] == "value"

    def test_preserves_existing_event_data(self) -> None:
        """Should preserve existing event dictionary data."""
        event_dict = {"event": "test_event", "custom_field": "custom_value"}
        result = add_opentelemetry_context(None, "warning", event_dict)

        assert result["event"] == "test_event"
        assert result["custom_field"] == "custom_value"


class TestAddServiceContext:
    """Tests for add_service_context processor."""

    def test_adds_default_service_name(self) -> None:
        """Should add default service name if not present."""
        event_dict = {"event": "test"}
        result = add_service_context(None, "info", event_dict)

        assert result["service"] == "retail-insights"

    def test_preserves_existing_service(self) -> None:
        """Should not overwrite existing service name."""
        event_dict = {"event": "test", "service": "custom-service"}
        result = add_service_context(None, "info", event_dict)

        assert result["service"] == "custom-service"
