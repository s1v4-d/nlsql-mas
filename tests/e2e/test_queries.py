"""End-to-end tests for query workflows.

These tests verify the complete query flow from user question to final answer,
testing common query patterns like aggregations, filters, and groupings.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# =============================================================================
# API Query Workflow Tests
# =============================================================================


class TestQueryAPIWorkflow:
    """E2E tests for the query API endpoint complete workflow."""

    def test_query_success_returns_answer(self, e2e_client: TestClient) -> None:
        """Test that a valid query returns a successful response with answer."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are the top 5 categories by revenue?"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["answer"] is not None
        assert len(data["answer"]) > 0
        assert data["sql_query"] is not None
        assert "SELECT" in data["sql_query"].upper()

    def test_query_includes_metadata(self, e2e_client: TestClient) -> None:
        """Test that query response includes proper metadata."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Show me all sales data"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "row_count" in data
        assert isinstance(data["row_count"], int)
        assert data["row_count"] >= 0

        # Check for standard response fields
        assert "session_id" in data
        assert data["session_id"] is not None
        assert "timestamp" in data

    def test_query_with_session_id(self, e2e_client: TestClient) -> None:
        """Test query with explicit session ID for continuity."""
        session_id = f"e2e-session-{uuid.uuid4().hex[:8]}"

        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What is the total revenue?", "session_id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_query_validates_input(self, e2e_client: TestClient) -> None:
        """Test that short/invalid questions are rejected."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "hi"},  # Too short
        )

        assert response.status_code == 422  # Validation error

    def test_query_handles_empty_question(self, e2e_client: TestClient) -> None:
        """Test that empty questions are rejected."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": ""},
        )

        assert response.status_code == 422


class TestQueryPatterns:
    """E2E tests for common query patterns."""

    def test_aggregation_query(self, e2e_client: TestClient) -> None:
        """Test aggregation queries (SUM, COUNT, AVG)."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What is the total revenue from all orders?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "SUM" in data["sql_query"].upper() or "total" in data["answer"].lower()

    def test_groupby_query(self, e2e_client: TestClient) -> None:
        """Test GROUP BY queries."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Show me sales breakdown by category"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_filter_query(self, e2e_client: TestClient) -> None:
        """Test queries with WHERE filters."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Show me cancelled orders"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_top_n_query(self, e2e_client: TestClient) -> None:
        """Test TOP N / LIMIT queries."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are the top 5 best selling categories?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        if data["sql_query"]:
            assert "LIMIT" in data["sql_query"].upper()

    def test_count_query(self, e2e_client: TestClient) -> None:
        """Test COUNT queries."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "How many orders were placed?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestSessionContinuity:
    """E2E tests for session and conversation continuity."""

    def test_multi_turn_same_session(self, e2e_client: TestClient) -> None:
        """Test multiple queries in the same session maintain context."""
        session_id = f"continuity-{uuid.uuid4().hex[:8]}"

        # First query
        r1 = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are the top categories by revenue?", "session_id": session_id},
        )
        assert r1.status_code == 200
        assert r1.json()["session_id"] == session_id

        # Second query in same session
        r2 = e2e_client.post(
            "/api/v1/query",
            json={"question": "Now show me the bottom 3", "session_id": session_id},
        )
        assert r2.status_code == 200
        assert r2.json()["session_id"] == session_id

    def test_different_sessions_isolated(self, e2e_client: TestClient) -> None:
        """Test that different session IDs are isolated."""
        session_1 = f"session-1-{uuid.uuid4().hex[:8]}"
        session_2 = f"session-2-{uuid.uuid4().hex[:8]}"

        r1 = e2e_client.post(
            "/api/v1/query",
            json={"question": "Show me revenue by category", "session_id": session_1},
        )
        r2 = e2e_client.post(
            "/api/v1/query",
            json={"question": "What is the total revenue?", "session_id": session_2},
        )

        assert r1.json()["session_id"] == session_1
        assert r2.json()["session_id"] == session_2
        assert r1.json()["session_id"] != r2.json()["session_id"]


class TestStreamingEndpoint:
    """E2E tests for the streaming query endpoint."""

    def test_stream_query_returns_events(self, e2e_client: TestClient) -> None:
        """Test that streaming endpoint returns SSE events."""
        response = e2e_client.post(
            "/api/v1/query/stream",
            json={"question": "What are the top categories?"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_stream_query_completes(self, e2e_client: TestClient) -> None:
        """Test that streaming query completes successfully."""
        with e2e_client.stream(
            "POST",
            "/api/v1/query/stream",
            json={"question": "What is the total revenue?"},
        ) as response:
            assert response.status_code == 200

            events = []
            for line in response.iter_lines():
                if line.startswith("data:"):
                    events.append(line)

            # Should have at least one event
            assert len(events) >= 1


# =============================================================================
# Performance Benchmarks
# =============================================================================


class TestQueryPerformance:
    """Performance-related E2E tests."""

    @pytest.mark.benchmark
    def test_query_response_time(self, e2e_client: TestClient) -> None:
        """Test that queries complete within acceptable time."""
        import time

        start = time.perf_counter()

        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What is the total revenue?"},
        )

        end = time.perf_counter()
        elapsed_ms = (end - start) * 1000

        assert response.status_code == 200
        # Should complete within 5 seconds (mocked LLM)
        assert elapsed_ms < 5000, f"Query took {elapsed_ms:.1f}ms, expected < 5000ms"

    @pytest.mark.benchmark
    def test_multiple_sequential_queries(self, e2e_client: TestClient) -> None:
        """Test multiple queries execute efficiently."""
        import time

        queries = [
            "What is the total revenue?",
            "Show me sales by category",
            "How many orders were cancelled?",
        ]

        start = time.perf_counter()

        for query in queries:
            response = e2e_client.post(
                "/api/v1/query",
                json={"question": query},
            )
            assert response.status_code == 200

        end = time.perf_counter()
        elapsed_ms = (end - start) * 1000

        # All 3 queries should complete within 10 seconds
        assert elapsed_ms < 10000, f"3 queries took {elapsed_ms:.1f}ms, expected < 10000ms"


# =============================================================================
# Health and Readiness Checks
# =============================================================================


class TestHealthEndpoints:
    """E2E tests for health and readiness endpoints."""

    def test_health_check(self, e2e_client: TestClient) -> None:
        """Test health endpoint returns healthy status."""
        response = e2e_client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_ready_check(self, e2e_client: TestClient) -> None:
        """Test readiness endpoint returns ready status."""
        response = e2e_client.get("/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"


# =============================================================================
# Concurrent Request Handling
# =============================================================================


class TestConcurrentRequests:
    """E2E tests for concurrent request handling."""

    def test_concurrent_queries(self, e2e_client: TestClient) -> None:
        """Test handling multiple concurrent query requests."""
        import concurrent.futures

        queries = [
            "What is the total revenue?",
            "Show me top 5 categories",
            "How many orders are there?",
            "What is the average order value?",
        ]

        def make_request(question: str):
            return e2e_client.post(
                "/api/v1/query",
                json={"question": question},
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(make_request, q) for q in queries]
            results = [f.result() for f in futures]

        # All requests should succeed
        for i, response in enumerate(results):
            assert response.status_code == 200, f"Query {i} failed: {response.text}"
            assert response.json()["success"] is True
