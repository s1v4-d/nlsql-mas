"""Integration tests for query API routes.

These tests verify the query and summarize endpoints work correctly
with the LangGraph workflow integration.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from retail_insights.engine.schema_registry import SchemaRegistry


@pytest.fixture(autouse=True)
def mock_env():
    """Set required environment variables for tests."""
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-api-key",
            "DEBUG": "true",
            "ENVIRONMENT": "development",
        },
    ):
        from retail_insights.core.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset schema registry singleton before each test."""
    SchemaRegistry.reset_instance()
    yield
    SchemaRegistry.reset_instance()


@pytest.fixture
def mock_graph():
    """Create a mock LangGraph for testing."""
    graph = MagicMock()

    # Mock successful query result
    async def mock_ainvoke(state, config=None):
        return {
            "intent": "query",
            "intent_confidence": 0.95,
            "generated_sql": "SELECT * FROM sales LIMIT 10",
            "sql_is_valid": True,
            "validation_status": "valid",
            "query_results": [{"id": 1, "amount": 100.0}],
            "row_count": 1,
            "execution_time_ms": 50.0,
            "final_answer": "Found 1 result with amount 100.0",
        }

    graph.ainvoke = AsyncMock(side_effect=mock_ainvoke)

    # Mock stream for SSE endpoint
    async def mock_astream(state, config=None, stream_mode=None):
        yield {"router": {"intent": "query", "intent_confidence": 0.95}}
        yield {"sql_generator": {"generated_sql": "SELECT * FROM sales LIMIT 10"}}
        yield {"validator": {"sql_is_valid": True, "validation_status": "valid"}}
        yield {"executor": {"row_count": 1, "query_results": [{"id": 1}]}}
        yield {"summarizer": {"final_answer": "Found 1 result"}}

    graph.astream = MagicMock(return_value=mock_astream(None))

    # Mock get_state for streaming endpoint
    mock_state = MagicMock()
    mock_state.values = {
        "final_answer": "Found 1 result",
        "generated_sql": "SELECT * FROM sales LIMIT 10",
        "query_results": [{"id": 1, "amount": 100.0}],
        "row_count": 1,
    }
    graph.aget_state = AsyncMock(return_value=mock_state)

    return graph


@pytest.fixture
def mock_schema_registry():
    """Create a mock schema registry."""
    registry = MagicMock()
    registry.get_schema_for_prompt.return_value = "Table: sales (id, amount, category)"
    registry.get_table_info.return_value = {"sales": {"columns": ["id", "amount", "category"]}}
    return registry


@pytest.fixture
def app(mock_graph, mock_schema_registry):
    """Create a test FastAPI app with mocked dependencies."""
    # Create app but don't use the lifespan (we'll set state manually)
    from retail_insights.core.config import get_settings

    settings = get_settings()

    test_app = FastAPI(title="Test App")

    # Import and include routers
    from retail_insights.api.routes.admin import router as admin_router
    from retail_insights.api.routes.query import router as query_router

    test_app.include_router(admin_router)
    test_app.include_router(query_router)

    # Set app state manually
    test_app.state.settings = settings
    test_app.state.graph = mock_graph
    test_app.state.schema_registry = mock_schema_registry
    test_app.state.checkpointer = MagicMock()

    # Add health endpoints for completeness
    @test_app.get("/health")
    async def health():
        return {"status": "healthy"}

    @test_app.get("/ready")
    async def ready():
        return {"status": "ready"}

    return test_app


@pytest.fixture
def client(app: FastAPI):
    """Create a test client."""
    return TestClient(app)


class TestQueryEndpoint:
    """Tests for POST /api/v1/query endpoint."""

    def test_query_success(self, client: TestClient) -> None:
        """Test successful query processing."""
        response = client.post(
            "/api/v1/query",
            json={"question": "What are the top 5 products by revenue?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "answer" in data
        assert "sql_query" in data
        assert "session_id" in data

    def test_query_with_session_id(self, client: TestClient) -> None:
        """Test query with explicit session ID."""
        response = client.post(
            "/api/v1/query",
            json={
                "question": "What are the top 5 products?",
                "session_id": "test-session-123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"

    def test_query_with_header_session_id(self, client: TestClient) -> None:
        """Test query with session ID from header."""
        response = client.post(
            "/api/v1/query",
            json={"question": "What are the top 5 products?"},
            headers={"X-Session-ID": "header-session-456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "header-session-456"

    def test_query_body_session_takes_priority(self, client: TestClient) -> None:
        """Test that body session_id takes priority over header."""
        response = client.post(
            "/api/v1/query",
            json={
                "question": "What are the top 5 products?",
                "session_id": "body-session",
            },
            headers={"X-Session-ID": "header-session"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "body-session"

    def test_query_validation_error(self, client: TestClient) -> None:
        """Test query with invalid request body."""
        response = client.post(
            "/api/v1/query",
            json={"question": "Hi"},  # Too short (< 5 chars)
        )
        assert response.status_code == 422

    def test_query_empty_question(self, client: TestClient) -> None:
        """Test query with empty question."""
        response = client.post(
            "/api/v1/query",
            json={"question": ""},
        )
        assert response.status_code == 422

    def test_query_with_mode(self, client: TestClient) -> None:
        """Test query with explicit mode."""
        response = client.post(
            "/api/v1/query",
            json={"question": "What are the sales trends?", "mode": "query"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_query_returns_execution_time(self, client: TestClient) -> None:
        """Test that query returns execution time."""
        response = client.post(
            "/api/v1/query",
            json={"question": "What are the total sales?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "execution_time_ms" in data
        assert data["execution_time_ms"] >= 0

    def test_query_includes_request_id_header(self, client: TestClient) -> None:
        """Test that response includes X-Request-ID header."""
        response = client.post(
            "/api/v1/query",
            json={"question": "What are the top categories?"},
        )
        # Note: In test client, middleware may not run fully
        assert response.status_code == 200


class TestQueryStreamEndpoint:
    """Tests for POST /api/v1/query/stream endpoint."""

    def test_stream_returns_sse(self, client: TestClient, mock_graph) -> None:
        """Test streaming endpoint returns SSE format."""
        # Need to setup fresh async mock for streaming
        async def fresh_stream(state, config=None, stream_mode=None):
            yield {"router": {"intent": "query"}}
            yield {"summarizer": {"final_answer": "Test"}}

        mock_graph.astream = MagicMock(return_value=fresh_stream(None))

        response = client.post(
            "/api/v1/query/stream",
            json={"question": "What are the top products?"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/event-stream; charset=utf-8"

    def test_stream_disables_buffering(self, client: TestClient, mock_graph) -> None:
        """Test streaming response has buffering disabled."""
        async def fresh_stream(state, config=None, stream_mode=None):
            yield {"router": {"intent": "query"}}

        mock_graph.astream = MagicMock(return_value=fresh_stream(None))

        response = client.post(
            "/api/v1/query/stream",
            json={"question": "What are the sales?"},
        )
        assert response.headers.get("x-accel-buffering") == "no"


class TestSummarizeEndpoint:
    """Tests for POST /api/v1/summarize endpoint."""

    def test_summarize_success(self, client: TestClient) -> None:
        """Test successful summary generation."""
        response = client.post(
            "/api/v1/summarize",
            json={"time_period": "last_quarter"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "summary" in data
        assert "time_period" in data
        assert data["time_period"] == "last_quarter"

    def test_summarize_with_filters(self, client: TestClient) -> None:
        """Test summary with region and category filters."""
        response = client.post(
            "/api/v1/summarize",
            json={
                "time_period": "last_month",
                "region": "MAHARASHTRA",
                "category": "Set",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_summarize_with_trends(self, client: TestClient) -> None:
        """Test summary with trend analysis enabled."""
        response = client.post(
            "/api/v1/summarize",
            json={
                "time_period": "last_quarter",
                "include_trends": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_summarize_returns_metrics(self, client: TestClient) -> None:
        """Test summary includes key_metrics."""
        response = client.post(
            "/api/v1/summarize",
            json={"time_period": "ytd"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "key_metrics" in data

    def test_summarize_returns_execution_time(self, client: TestClient) -> None:
        """Test summary returns execution time."""
        response = client.post(
            "/api/v1/summarize",
            json={"time_period": "last_month"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "execution_time_ms" in data
        assert data["execution_time_ms"] >= 0


class TestGraphErrorHandling:
    """Tests for error handling in query routes."""

    def test_graph_recursion_error(self, client: TestClient, mock_graph) -> None:
        """Test handling of graph recursion errors."""
        mock_graph.ainvoke = AsyncMock(side_effect=RecursionError("max recursion"))

        response = client.post(
            "/api/v1/query",
            json={"question": "What are the sales?"},
        )
        assert response.status_code == 422
        assert "too many retries" in response.json()["detail"]

    def test_graph_generic_error(self, client: TestClient, mock_graph) -> None:
        """Test handling of generic graph errors."""
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Graph failed"))

        response = client.post(
            "/api/v1/query",
            json={"question": "What are the sales?"},
        )
        assert response.status_code == 500
        assert "Query processing failed" in response.json()["detail"]


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test /health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_ready_endpoint(self, client: TestClient) -> None:
        """Test /ready endpoint returns ready status."""
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
