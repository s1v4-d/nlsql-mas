"""Tests for API middleware."""

from __future__ import annotations

import pytest

from retail_insights.api.middleware import (
    get_request_id,
    request_id_var,
)


class TestRequestIdVar:
    """Tests for request_id context variable."""

    def test_get_request_id_returns_current_value(self) -> None:
        """Should return current request ID from context."""
        token = request_id_var.set("test-request-123")
        try:
            result = get_request_id()
            assert result == "test-request-123"
        finally:
            request_id_var.reset(token)

    def test_get_request_id_returns_default_when_unset(self) -> None:
        """Should return empty string when not set."""
        result = get_request_id()
        assert result == ""


class TestRequestContextMiddleware:
    """Tests for RequestContextMiddleware initialization."""

    def test_middleware_can_be_instantiated(self) -> None:
        """Should be able to create middleware instance."""
        from retail_insights.api.middleware import RequestContextMiddleware
        from unittest.mock import MagicMock

        mock_app = MagicMock()
        middleware = RequestContextMiddleware(mock_app)
        assert middleware is not None
        assert hasattr(middleware, "dispatch")
