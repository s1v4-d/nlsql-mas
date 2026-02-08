"""Unit tests for input sanitization."""

import pytest
from pydantic import ValidationError

from retail_insights.models.requests import (
    QueryRequest,
    SummarizeRequest,
    sanitize_input,
)


class TestSanitizeInput:
    """Tests for input sanitization function."""

    def test_allows_normal_text(self):
        """Test normal text passes validation."""
        result = sanitize_input("What were the top sales in Q3?")
        assert result == "What were the top sales in Q3?"

    def test_allows_question_with_numbers(self):
        """Test questions with numbers pass."""
        result = sanitize_input("Show me sales for product ID 12345")
        assert result == "Show me sales for product ID 12345"

    def test_blocks_sql_comment_dash(self):
        """Test blocks SQL double-dash comment."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("Some query -- DROP TABLE users")

    def test_blocks_drop_table(self):
        """Test blocks DROP TABLE statement."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("Show sales; DROP TABLE users")

    def test_blocks_union_select(self):
        """Test blocks UNION SELECT injection."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("' UNION SELECT * FROM users")

    def test_blocks_or_1_equals_1(self):
        """Test blocks classic OR injection."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("' OR '1'='1")

    def test_blocks_script_tag(self):
        """Test blocks script tags."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("Hello <script>alert('xss')</script>")

    def test_blocks_javascript_protocol(self):
        """Test blocks javascript: protocol."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("Click here javascript:alert(1)")

    def test_blocks_event_handlers(self):
        """Test blocks event handler attributes."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("<img onerror=alert(1)>")

    def test_blocks_iframe(self):
        """Test blocks iframe tags."""
        with pytest.raises(ValueError, match="unsafe"):
            sanitize_input("<iframe src='evil.com'>")

    def test_allows_sql_keywords_in_context(self):
        """Test allows SQL keywords when used normally."""
        result = sanitize_input("What categories should I select for the report?")
        assert "select" in result.lower()


class TestQueryRequestValidation:
    """Tests for QueryRequest input validation."""

    def test_valid_query(self):
        """Test valid query passes validation."""
        request = QueryRequest(question="What were the top 5 categories by revenue?")
        assert request.question == "What were the top 5 categories by revenue?"

    def test_rejects_sql_injection(self):
        """Test rejects SQL injection attempts."""
        with pytest.raises(ValidationError):
            QueryRequest(question="'; DROP TABLE users--")

    def test_rejects_xss(self):
        """Test rejects XSS attempts."""
        with pytest.raises(ValidationError):
            QueryRequest(question="<script>alert('xss')</script>")

    def test_valid_session_id(self):
        """Test valid session ID passes."""
        request = QueryRequest(
            question="Show me sales data",
            session_id="abc-123_XYZ",
        )
        assert request.session_id == "abc-123_XYZ"

    def test_rejects_invalid_session_id(self):
        """Test rejects session ID with invalid characters."""
        with pytest.raises(ValidationError):
            QueryRequest(
                question="Show me sales data",
                session_id="invalid;session<>id",
            )


class TestSummarizeRequestValidation:
    """Tests for SummarizeRequest input validation."""

    def test_valid_request(self):
        """Test valid summarize request passes."""
        request = SummarizeRequest(
            time_period="last_quarter",
            region="California",
            category="Electronics",
        )
        assert request.time_period == "last_quarter"

    def test_rejects_sql_injection_in_filters(self):
        """Test rejects SQL injection in filter fields."""
        with pytest.raises(ValidationError):
            SummarizeRequest(
                time_period="last_quarter",
                region="'; DROP TABLE sales--",
            )

    def test_rejects_xss_in_category(self):
        """Test rejects XSS in category field."""
        with pytest.raises(ValidationError):
            SummarizeRequest(
                category="<script>alert(1)</script>",
            )
