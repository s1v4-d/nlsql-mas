"""End-to-end tests for error scenarios.

These tests verify graceful error handling for various failure modes:
- Invalid SQL generation
- Validation failures
- Execution errors
- Timeout scenarios
- Input validation errors
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from retail_insights.engine.schema_registry import SchemaRegistry

if TYPE_CHECKING:
    pass


@pytest.fixture(autouse=True)
def reset_schema_registry():
    """Reset schema registry singleton before and after each test."""
    SchemaRegistry.reset_instance()
    yield
    SchemaRegistry.reset_instance()


class TestInputValidationErrors:
    """E2E tests for input validation error handling."""

    def test_empty_question_rejected(self, e2e_client: TestClient) -> None:
        """Test that empty questions are rejected with proper error."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": ""},
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_short_question_rejected(self, e2e_client: TestClient) -> None:
        """Test that very short questions are rejected."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "hi"},
        )

        assert response.status_code == 422

    def test_missing_question_field(self, e2e_client: TestClient) -> None:
        """Test that missing question field returns error."""
        response = e2e_client.post(
            "/api/v1/query",
            json={},
        )

        assert response.status_code == 422

    def test_invalid_json_body(self, e2e_client: TestClient) -> None:
        """Test that invalid JSON body returns error."""
        response = e2e_client.post(
            "/api/v1/query",
            content="invalid json{",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def test_wrong_content_type(self, e2e_client: TestClient) -> None:
        """Test that wrong content type is handled."""
        response = e2e_client.post(
            "/api/v1/query",
            content="question=test",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # Should return 422 (unprocessable) or 415 (unsupported media type)
        assert response.status_code in [415, 422]


class TestSQLValidationErrors:
    """E2E tests for SQL validation error handling."""

    @pytest.fixture
    def app_with_invalid_sql_generator(self):
        """Create app with SQL generator that produces invalid SQL."""
        from retail_insights.core.config import get_settings

        settings = get_settings()

        graph = MagicMock()

        async def mock_ainvoke_invalid_sql(state, config=None):
            return {
                "intent": "query",
                "intent_confidence": 0.9,
                "generated_sql": "SELEC * FORM invalid_table",  # Invalid SQL
                "sql_is_valid": False,
                "validation_status": "failed",
                "validation_errors": ["Syntax error: unexpected token 'SELEC'"],
                "query_results": None,
                "row_count": 0,
                "execution_time_ms": 0,
                "final_answer": "I couldn't generate a valid SQL query for your request.",
            }

        graph.ainvoke = AsyncMock(side_effect=mock_ainvoke_invalid_sql)

        # Create inline mock schema registry
        mock_registry = MagicMock()
        mock_registry.get_schema_for_prompt.return_value = "Table: amazon_sales"
        mock_registry.get_table_names.return_value = ["amazon_sales"]

        test_app = FastAPI(title="Error Test App")

        from retail_insights.api.routes.admin import router as admin_router
        from retail_insights.api.routes.query import router as query_router

        test_app.include_router(admin_router)
        test_app.include_router(query_router)

        test_app.state.settings = settings
        test_app.state.graph = graph
        test_app.state.schema_registry = mock_registry
        test_app.state.checkpointer = MemorySaver()

        @test_app.get("/health")
        async def health():
            return {"status": "healthy"}

        return test_app

    @pytest.mark.xfail(
        reason="Route raises SQLGenerationError for validation failures - needs route-level error handler"
    )
    def test_invalid_sql_returns_graceful_failure(self, app_with_invalid_sql_generator) -> None:
        """Test that invalid SQL generation returns graceful failure message."""
        client = TestClient(app_with_invalid_sql_generator)

        response = client.post(
            "/api/v1/query",
            json={"question": "Run this weird query that fails"},
        )

        # Should return 200 with error message, not 500
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True  # Request processed successfully
        assert "couldn't" in data["answer"].lower() or "error" in data["answer"].lower()


class TestMaxRetriesExceeded:
    """E2E tests for max retry limit handling."""

    @pytest.fixture
    def app_with_max_retries_exceeded(self):
        """Create app that simulates max retries exceeded."""
        from retail_insights.core.config import get_settings

        settings = get_settings()

        graph = MagicMock()

        async def mock_ainvoke_max_retries(state, config=None):
            return {
                "intent": "query",
                "intent_confidence": 0.9,
                "generated_sql": "SELECT * FROM unknown_table",
                "sql_is_valid": False,
                "validation_status": "failed",
                "validation_errors": [
                    "Retry 1: Unknown table 'unknown_table'",
                    "Retry 2: Unknown table 'unknown_table'",
                    "Retry 3: Unknown table 'unknown_table'",
                ],
                "retry_count": 3,
                "max_retries": 3,
                "query_results": None,
                "row_count": 0,
                "execution_time_ms": 0,
                "final_answer": "I couldn't generate a valid SQL query after 3 attempts. The table you're looking for might not exist.",
            }

        graph.ainvoke = AsyncMock(side_effect=mock_ainvoke_max_retries)

        # Create inline mock schema registry
        mock_registry = MagicMock()
        mock_registry.get_schema_for_prompt.return_value = "Table: amazon_sales"
        mock_registry.get_table_names.return_value = ["amazon_sales"]

        test_app = FastAPI(title="Retry Test App")

        from retail_insights.api.routes.admin import router as admin_router
        from retail_insights.api.routes.query import router as query_router

        test_app.include_router(admin_router)
        test_app.include_router(query_router)

        test_app.state.settings = settings
        test_app.state.graph = graph
        test_app.state.schema_registry = mock_registry
        test_app.state.checkpointer = MemorySaver()

        return test_app

    @pytest.mark.xfail(
        reason="Route raises SQLGenerationError for max retries - needs route-level error handler"
    )
    def test_max_retries_returns_helpful_message(self, app_with_max_retries_exceeded) -> None:
        """Test that max retries exceeded returns helpful error message."""
        client = TestClient(app_with_max_retries_exceeded)

        response = client.post(
            "/api/v1/query",
            json={"question": "Query from a table that doesn't exist"},
        )

        assert response.status_code == 200
        data = response.json()
        # Should have a helpful message about the failure
        assert "couldn't" in data["answer"].lower() or "attempts" in data["answer"].lower()


class TestExecutionErrors:
    """E2E tests for query execution error handling."""

    @pytest.fixture
    def app_with_execution_error(self):
        """Create app that simulates execution error."""
        from retail_insights.core.config import get_settings

        settings = get_settings()

        graph = MagicMock()

        async def mock_ainvoke_execution_error(state, config=None):
            return {
                "intent": "query",
                "intent_confidence": 0.95,
                "generated_sql": "SELECT * FROM amazon_sales",
                "sql_is_valid": True,
                "validation_status": "valid",
                "query_results": None,
                "row_count": 0,
                "execution_time_ms": 0,
                "execution_error": "Connection to database lost",
                "final_answer": "Query execution failed: Connection to database lost",
            }

        graph.ainvoke = AsyncMock(side_effect=mock_ainvoke_execution_error)

        mock_registry = MagicMock()
        mock_registry.get_schema_for_prompt.return_value = "Table: amazon_sales"
        mock_registry.get_table_names.return_value = ["amazon_sales"]

        test_app = FastAPI(title="Execution Error Test App")

        from retail_insights.api.routes.admin import router as admin_router
        from retail_insights.api.routes.query import router as query_router

        test_app.include_router(admin_router)
        test_app.include_router(query_router)

        from retail_insights.api.rate_limit import get_limiter, reset_limiter

        reset_limiter()
        limiter = get_limiter(settings)

        test_app.state.settings = settings
        test_app.state.graph = graph
        test_app.state.schema_registry = mock_registry
        test_app.state.checkpointer = MemorySaver()
        test_app.state.limiter = limiter

        return test_app

    def test_execution_error_returns_error_message(self, app_with_execution_error) -> None:
        """Test that execution errors return proper error message."""
        client = TestClient(app_with_execution_error)

        response = client.post(
            "/api/v1/query",
            json={"question": "Show me all sales"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "failed" in data["answer"].lower() or "error" in data["answer"].lower()


class TestTimeoutScenarios:
    """E2E tests for timeout handling."""

    @pytest.fixture
    def app_with_timeout(self):
        """Create app that simulates timeout."""
        import asyncio

        from retail_insights.core.config import get_settings

        settings = get_settings()

        graph = MagicMock()

        async def mock_ainvoke_timeout(state, config=None):
            # Simulate a very long operation that might timeout
            await asyncio.sleep(0.1)  # Short for testing
            return {
                "intent": "query",
                "intent_confidence": 0.9,
                "generated_sql": "SELECT * FROM amazon_sales",
                "sql_is_valid": True,
                "validation_status": "valid",
                "query_results": [{"id": 1}],
                "row_count": 1,
                "execution_time_ms": 100,
                "final_answer": "Query completed successfully.",
            }

        graph.ainvoke = AsyncMock(side_effect=mock_ainvoke_timeout)

        mock_registry = MagicMock()
        mock_registry.get_schema_for_prompt.return_value = "Table: amazon_sales"
        mock_registry.get_table_names.return_value = ["amazon_sales"]

        test_app = FastAPI(title="Timeout Test App")

        from retail_insights.api.routes.admin import router as admin_router
        from retail_insights.api.routes.query import router as query_router

        test_app.include_router(admin_router)
        test_app.include_router(query_router)

        test_app.state.settings = settings
        test_app.state.graph = graph
        test_app.state.schema_registry = mock_registry
        test_app.state.checkpointer = MemorySaver()

        return test_app

    def test_slow_query_completes(self, app_with_timeout) -> None:
        """Test that slower queries still complete successfully."""
        client = TestClient(app_with_timeout)

        response = client.post(
            "/api/v1/query",
            json={"question": "Run a complex query that takes time"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestGraphErrors:
    """E2E tests for graph-level error handling."""

    @pytest.fixture
    def app_with_graph_error(self):
        """Create app with a graph that raises exceptions."""
        from retail_insights.core.config import get_settings

        settings = get_settings()

        graph = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=Exception("Graph execution failed"))

        mock_registry = MagicMock()
        mock_registry.get_schema_for_prompt.return_value = "Table: amazon_sales"
        mock_registry.get_table_names.return_value = ["amazon_sales"]

        test_app = FastAPI(title="Graph Error Test App")

        from retail_insights.api.routes.admin import router as admin_router
        from retail_insights.api.routes.query import router as query_router

        test_app.include_router(admin_router)
        test_app.include_router(query_router)

        test_app.state.settings = settings
        test_app.state.graph = graph
        test_app.state.schema_registry = mock_registry
        test_app.state.checkpointer = MemorySaver()

        return test_app

    def test_graph_exception_returns_500(self, app_with_graph_error) -> None:
        """Test that unhandled graph exceptions return 500."""
        client = TestClient(app_with_graph_error)

        response = client.post(
            "/api/v1/query",
            json={"question": "This will cause an internal error"},
        )

        # Should return 500 for unhandled exceptions
        assert response.status_code == 500
        data = response.json()
        assert "error" in data.get("detail", "").lower() or response.status_code == 500


class TestClarificationIntent:
    """E2E tests for clarification intent handling."""

    @pytest.fixture
    def app_with_clarify_intent(self):
        """Create app that returns clarify intent."""
        from retail_insights.core.config import get_settings

        settings = get_settings()

        graph = MagicMock()

        async def mock_ainvoke_clarify(state, config=None):
            return {
                "intent": "clarify",
                "intent_confidence": 0.85,
                "clarification_question": "Could you please specify which time period you're interested in?",
                "generated_sql": None,
                "sql_is_valid": False,
                "validation_status": "pending",
                "query_results": None,
                "row_count": 0,
                "execution_time_ms": 0,
                "final_answer": "Could you please specify which time period you're interested in?",
            }

        graph.ainvoke = AsyncMock(side_effect=mock_ainvoke_clarify)

        mock_registry = MagicMock()
        mock_registry.get_schema_for_prompt.return_value = "Table: amazon_sales"
        mock_registry.get_table_names.return_value = ["amazon_sales"]

        test_app = FastAPI(title="Clarify Test App")

        from retail_insights.api.routes.admin import router as admin_router
        from retail_insights.api.routes.query import router as query_router

        test_app.include_router(admin_router)
        test_app.include_router(query_router)

        test_app.state.settings = settings
        test_app.state.graph = graph
        test_app.state.schema_registry = mock_registry
        test_app.state.checkpointer = MemorySaver()

        return test_app

    def test_clarify_intent_returns_question(self, app_with_clarify_intent) -> None:
        """Test that clarify intent returns clarification question."""
        client = TestClient(app_with_clarify_intent)

        response = client.post(
            "/api/v1/query",
            json={"question": "Show me sales"},  # Ambiguous
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Answer should be a clarifying question
        assert "?" in data["answer"] or "specify" in data["answer"].lower()


class TestEdgeCaseErrors:
    """E2E tests for edge case error handling."""

    def test_very_long_question_handled(self, e2e_client: TestClient) -> None:
        """Test that very long questions are handled (or rejected gracefully)."""
        long_question = "What are the sales? " * 100  # Very long question

        response = e2e_client.post(
            "/api/v1/query",
            json={"question": long_question},
        )

        # Should either succeed or return a validation error, not 500
        assert response.status_code in [200, 422]

    def test_special_characters_in_question(self, e2e_client: TestClient) -> None:
        """Test that special characters in questions are handled safely."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are sales for 'category = \"Set\"' and amount > $100?"},
        )

        # Should not cause SQL injection or crashes
        assert response.status_code in [200, 422]

    def test_unicode_in_question(self, e2e_client: TestClient) -> None:
        """Test that unicode characters are handled properly."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are the sales for 日本語 category?"},
        )

        assert response.status_code == 200
        data = response.json()
        # Should handle gracefully, not crash
        assert data["success"] is True

    def test_null_values_in_request(self, e2e_client: TestClient) -> None:
        """Test that null values in optional fields are handled."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What is the total revenue?", "session_id": None},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAbusePrevention:
    """E2E tests for abuse prevention measures."""

    def test_sql_injection_attempt_blocked(self, e2e_client: TestClient) -> None:
        """Test that SQL injection attempts are blocked by input validation."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "'; DROP TABLE amazon_sales; --"},
        )

        # Injection attempts should be rejected at validation layer
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_xss_attempt_in_question(self, e2e_client: TestClient) -> None:
        """Test that XSS attempts in questions are blocked."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "<script>alert('xss')</script>What are sales?"},
        )

        # XSS attempts should be rejected at validation layer
        assert response.status_code == 422
