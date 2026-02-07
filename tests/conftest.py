"""Pytest fixtures for the test suite."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from retail_insights.core.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    return Settings(
        OPENAI_API_KEY="test-api-key",  # type: ignore
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        ENVIRONMENT="development",
        DATABASE_URL="postgresql://test:test@localhost:5432/test",
        REDIS_URL="redis://localhost:6379/0",
        S3_DATA_PATH="s3://test-bucket/data",
        LOCAL_DATA_PATH="tests/fixtures/data",
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLM client for testing."""
    client = MagicMock()
    client.ainvoke = AsyncMock(return_value="Mock response")
    client.invoke = MagicMock(return_value="Mock response")
    client.ainvoke_structured = AsyncMock()
    client.invoke_structured = MagicMock()
    return client


@pytest.fixture
def sample_query_data() -> list[dict]:
    """Sample query result data for testing."""
    return [
        {"Category": "Set", "revenue": 2100000.0},
        {"Category": "kurta", "revenue": 1800000.0},
        {"Category": "Western Dress", "revenue": 950000.0},
        {"Category": "Blouse", "revenue": 720000.0},
        {"Category": "Top", "revenue": 580000.0},
    ]


@pytest.fixture
def sample_sql() -> str:
    """Sample SQL query for testing."""
    return """
    SELECT Category, SUM(Amount) as revenue
    FROM amazon_sales
    GROUP BY Category
    ORDER BY revenue DESC
    LIMIT 5
    """
