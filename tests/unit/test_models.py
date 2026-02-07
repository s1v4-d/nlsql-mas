"""Unit tests for Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from retail_insights.models.agents import (
    ExecutionResult,
    Intent,
    RouterDecision,
    SQLGenerationResult,
    ValidationResult,
)
from retail_insights.models.requests import (
    QueryMode,
    QueryRequest,
    SummarizeRequest,
)
from retail_insights.models.responses import (
    ErrorResponse,
    QueryResult,
)


class TestQueryRequest:
    """Tests for QueryRequest model."""

    def test_valid_query_request(self) -> None:
        """Test creating a valid QueryRequest."""
        request = QueryRequest(
            question="What were the top 5 categories by revenue?",
            mode=QueryMode.QUERY,
            session_id="test-session",
            max_results=50,
        )
        assert request.question == "What were the top 5 categories by revenue?"
        assert request.mode == QueryMode.QUERY
        assert request.session_id == "test-session"
        assert request.max_results == 50

    def test_default_values(self) -> None:
        """Test QueryRequest default values."""
        request = QueryRequest(question="What is the total revenue?")
        assert request.mode == QueryMode.QUERY
        assert request.session_id is None
        assert request.max_results == 100

    def test_question_too_short(self) -> None:
        """Test validation for question that's too short."""
        with pytest.raises(PydanticValidationError) as exc_info:
            QueryRequest(question="Hi")
        assert "String should have at least 5 characters" in str(exc_info.value)

    def test_question_too_long(self) -> None:
        """Test validation for question that's too long."""
        with pytest.raises(PydanticValidationError):
            QueryRequest(question="x" * 2001)

    def test_max_results_bounds(self) -> None:
        """Test max_results validation bounds."""
        # Too low
        with pytest.raises(PydanticValidationError):
            QueryRequest(question="Valid question", max_results=0)

        # Too high
        with pytest.raises(PydanticValidationError):
            QueryRequest(question="Valid question", max_results=10001)


class TestSummarizeRequest:
    """Tests for SummarizeRequest model."""

    def test_default_values(self) -> None:
        """Test SummarizeRequest default values."""
        request = SummarizeRequest()
        assert request.time_period == "last_quarter"
        assert request.region is None
        assert request.category is None
        assert request.include_trends is True

    def test_with_filters(self) -> None:
        """Test SummarizeRequest with filters."""
        request = SummarizeRequest(
            time_period="last_month",
            region="MAHARASHTRA",
            category="Set",
            include_trends=False,
        )
        assert request.time_period == "last_month"
        assert request.region == "MAHARASHTRA"
        assert request.category == "Set"
        assert request.include_trends is False


class TestQueryResult:
    """Tests for QueryResult model."""

    def test_successful_result(self) -> None:
        """Test creating a successful QueryResult."""
        result = QueryResult(
            success=True,
            answer="The top category is Set with $2.1M revenue.",
            sql_query="SELECT Category FROM amazon_sales",
            data=[{"Category": "Set", "revenue": 2100000}],
            row_count=1,
            execution_time_ms=150.5,
            session_id="test-session",
        )
        assert result.success is True
        assert result.row_count == 1
        assert result.execution_time_ms == 150.5
        assert isinstance(result.timestamp, datetime)

    def test_failed_result(self) -> None:
        """Test creating a failed QueryResult."""
        result = QueryResult(
            success=False,
            answer="Could not generate a valid SQL query.",
            execution_time_ms=50.0,
        )
        assert result.success is False
        assert result.data is None
        assert result.sql_query is None


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_error_response(self) -> None:
        """Test creating an error response."""
        error = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Invalid SQL syntax",
            details={"line": 1, "column": 15},
        )
        assert error.success is False
        assert error.error_code == "VALIDATION_ERROR"
        assert error.details["line"] == 1


class TestRouterDecision:
    """Tests for RouterDecision model."""

    def test_query_intent(self) -> None:
        """Test RouterDecision with query intent."""
        decision = RouterDecision(
            intent=Intent.QUERY,
            confidence=0.95,
            reasoning="User is asking for specific sales data",
        )
        assert decision.intent == Intent.QUERY
        assert decision.confidence == 0.95
        assert decision.clarification_question is None

    def test_clarify_intent(self) -> None:
        """Test RouterDecision with clarify intent."""
        decision = RouterDecision(
            intent=Intent.CLARIFY,
            confidence=0.7,
            reasoning="Query is ambiguous",
            clarification_question="Did you mean revenue or quantity?",
        )
        assert decision.intent == Intent.CLARIFY
        assert decision.clarification_question is not None

    def test_confidence_bounds(self) -> None:
        """Test confidence score validation."""
        with pytest.raises(PydanticValidationError):
            RouterDecision(
                intent=Intent.QUERY,
                confidence=1.5,  # Invalid: > 1.0
                reasoning="Test",
            )


class TestSQLGenerationResult:
    """Tests for SQLGenerationResult model."""

    def test_valid_result(self) -> None:
        """Test creating a valid SQLGenerationResult."""
        result = SQLGenerationResult(
            sql_query="SELECT Category, SUM(Amount) FROM amazon_sales GROUP BY Category",
            explanation="Calculates total sales by category",
            tables_used=["amazon_sales"],
            columns_used=["Category", "Amount"],
            assumptions="Using Amount as revenue column",
        )
        assert "SELECT" in result.sql_query
        assert len(result.tables_used) == 1
        assert "Category" in result.columns_used

    def test_sql_too_short(self) -> None:
        """Test SQL query minimum length validation."""
        with pytest.raises(PydanticValidationError):
            SQLGenerationResult(
                sql_query="SELECT",  # Too short
                explanation="Test",
            )


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_valid_sql(self) -> None:
        """Test validation result for valid SQL."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["LIMIT clause added"],
            corrected_sql="SELECT * FROM amazon_sales LIMIT 100",
            tables_validated=["amazon_sales"],
        )
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert "LIMIT clause added" in result.warnings

    def test_invalid_sql(self) -> None:
        """Test validation result for invalid SQL."""
        result = ValidationResult(
            is_valid=False,
            errors=["Unknown table: sales", "Syntax error at line 1"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 2


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_successful_execution(self) -> None:
        """Test successful query execution result."""
        result = ExecutionResult(
            success=True,
            row_count=5,
            columns=["Category", "revenue"],
            data=[
                {"Category": "Set", "revenue": 2100000},
                {"Category": "kurta", "revenue": 1800000},
            ],
            execution_time_ms=123.45,
        )
        assert result.success is True
        assert result.row_count == 5
        assert len(result.columns) == 2

    def test_failed_execution(self) -> None:
        """Test failed query execution result."""
        result = ExecutionResult(
            success=False,
            error_message="Table not found: amazon_sale",
        )
        assert result.success is False
        assert result.error_message is not None
        assert result.row_count == 0
