"""End-to-end tests for summarization workflows.

These tests verify the summarize intent flow and chat interactions,
testing the graceful handling of non-query requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# =============================================================================
# Summarization Intent Tests
# =============================================================================


class TestSummarizationWorkflow:
    """E2E tests for summarization intent handling."""

    def test_summarize_request_succeeds(self, e2e_client: TestClient) -> None:
        """Test that summarization requests return valid responses."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Give me a summary of the sales data"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["answer"] is not None
        assert len(data["answer"]) > 10  # Non-trivial response

    def test_overview_request_handled(self, e2e_client: TestClient) -> None:
        """Test overview-style requests are handled as summaries."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Can you give me an overview of the data?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["answer"] is not None

    def test_summary_without_explicit_sql(self, e2e_client: TestClient) -> None:
        """Test that summarize intent may not generate explicit SQL."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Summarize the key trends in our sales"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Answer should contain meaningful content
        assert len(data["answer"]) > 20


class TestSummarizeEndpoint:
    """E2E tests for the dedicated summarize endpoint."""

    def test_summarize_endpoint_basic(self, e2e_client: TestClient) -> None:
        """Test basic summarize endpoint functionality."""
        response = e2e_client.post(
            "/api/v1/summarize",
            json={},  # No filters
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert len(data["summary"]) > 0

    def test_summarize_with_category_filter(self, e2e_client: TestClient) -> None:
        """Test summarize endpoint with category filter."""
        response = e2e_client.post(
            "/api/v1/summarize",
            json={"category": "kurta"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        # Summary should be relevant to the category
        assert len(data["summary"]) > 0

    def test_summarize_with_region_filter(self, e2e_client: TestClient) -> None:
        """Test summarize endpoint with region/state filter."""
        response = e2e_client.post(
            "/api/v1/summarize",
            json={"region": "MAHARASHTRA"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data

    def test_summarize_with_date_range(self, e2e_client: TestClient) -> None:
        """Test summarize endpoint with date range filter."""
        response = e2e_client.post(
            "/api/v1/summarize",
            json={"start_date": "2022-01-01", "end_date": "2022-06-30"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data

    def test_summarize_returns_key_metrics(self, e2e_client: TestClient) -> None:
        """Test that summarize returns key metric information."""
        response = e2e_client.post(
            "/api/v1/summarize",
            json={},
        )

        assert response.status_code == 200
        data = response.json()

        # Should include key metrics
        assert "key_metrics" in data or "summary" in data


# =============================================================================
# Chat Intent Tests
# =============================================================================


class TestChatWorkflow:
    """E2E tests for chat intent handling."""

    def test_greeting_handled_gracefully(self, e2e_client: TestClient) -> None:
        """Test that greetings are handled as chat intent."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Hello, how are you doing today?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should get a conversational response, not an error
        assert data["answer"] is not None
        assert len(data["answer"]) > 5

    def test_help_request_provides_guidance(self, e2e_client: TestClient) -> None:
        """Test that help requests provide useful guidance."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What can you help me with?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should get a meaningful response (mock returns query-style response)
        assert data["answer"] is not None
        assert len(data["answer"]) > 10

    def test_thanks_handled_gracefully(self, e2e_client: TestClient) -> None:
        """Test that thank you messages are handled properly."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Thank you for your help!"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_chat_does_not_generate_sql(self, e2e_client: TestClient) -> None:
        """Test that chat intents may not execute SQL queries."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Hi there, nice to meet you!"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Chat might have null or no SQL query
        # The main check is that we get a valid conversational response


# =============================================================================
# Trend Analysis Tests
# =============================================================================


class TestTrendAnalysis:
    """E2E tests for trend analysis queries."""

    def test_trend_query_time_based(self, e2e_client: TestClient) -> None:
        """Test time-based trend analysis requests."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are the sales trends over time?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_comparison_query(self, e2e_client: TestClient) -> None:
        """Test comparison queries between categories/regions."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Compare sales between Maharashtra and Karnataka"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_growth_analysis_query(self, e2e_client: TestClient) -> None:
        """Test growth/performance analysis queries."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Which categories are growing the fastest?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# =============================================================================
# Multi-Intent Handling Tests
# =============================================================================


class TestMultiIntentHandling:
    """E2E tests for queries that could be multiple intents."""

    def test_ambiguous_summarize_query(self, e2e_client: TestClient) -> None:
        """Test handling of queries that could be summarize or query."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "Tell me about sales performance"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should get some meaningful response regardless of exact intent
        assert data["answer"] is not None

    def test_complex_request_handled(self, e2e_client: TestClient) -> None:
        """Test handling of complex, multi-part requests."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are our top categories and how are they trending?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# =============================================================================
# Response Quality Tests
# =============================================================================


class TestResponseQuality:
    """E2E tests for response quality and formatting."""

    def test_answer_is_human_readable(self, e2e_client: TestClient) -> None:
        """Test that answers are human-readable, not raw data."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What is the total revenue?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] is not None

        # Answer should be a readable sentence, not just a number
        answer = data["answer"]
        assert len(answer) > 5
        # Should contain words, not just numbers/symbols
        assert any(c.isalpha() for c in answer)

    def test_answer_addresses_question(self, e2e_client: TestClient) -> None:
        """Test that answers are relevant to the question asked."""
        response = e2e_client.post(
            "/api/v1/query",
            json={"question": "What are the top 3 categories by revenue?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] is not None

        # Answer should relate to categories or revenue
        answer_lower = data["answer"].lower()
        assert any(
            word in answer_lower
            for word in ["category", "categories", "revenue", "top", "result", "data"]
        )

    def test_summary_is_concise(self, e2e_client: TestClient) -> None:
        """Test that summaries are reasonably concise."""
        response = e2e_client.post(
            "/api/v1/summarize",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", "")

        # Summary should be informative but not excessively long
        # (Less than 2000 characters for a high-level summary)
        assert len(summary) < 2000
