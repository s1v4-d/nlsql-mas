"""Integration test fixtures."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_env():
    """Set required environment variables for integration tests."""
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-integration-api-key",
            "DEBUG": "true",
            "ENVIRONMENT": "development",
        },
    ):
        from retail_insights.core.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()
