"""Integration tests for the Executor agent node.

These tests use an in-memory DuckDB instance with sample data
to verify end-to-end query execution functionality.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from retail_insights.agents.nodes.executor import (
    DuckDBErrorType,
    _classify_error,
    _format_error_for_llm,
    _sanitize_row,
    _sanitize_value,
    create_mock_executor,
    execute_query,
)
from retail_insights.engine.connector import DuckDBConnector
from retail_insights.engine.query_runner import QueryRunner


@pytest.fixture
def temp_parquet_file(tmp_path: Path) -> Path:
    """Create a temporary Parquet file with sample data."""
    import duckdb

    file_path = tmp_path / "sample_sales.parquet"

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE sample_data AS
        SELECT *
        FROM (VALUES
            (1, 'Widget A', 'Electronics', 99.99, 10, DATE '2024-01-01'),
            (2, 'Widget B', 'Electronics', 149.99, 5, DATE '2024-01-02'),
            (3, 'Gadget X', 'Accessories', 29.99, 20, DATE '2024-01-03'),
            (4, 'Gadget Y', 'Accessories', 39.99, 15, DATE '2024-01-04'),
            (5, 'Device Z', 'Electronics', 299.99, 3, DATE '2024-01-05')
        ) AS t(id, product_name, category, price, quantity, sale_date)
    """)
    conn.execute(f"COPY sample_data TO '{file_path}' (FORMAT PARQUET)")
    conn.close()

    return file_path


@pytest.fixture
def duckdb_connector(temp_parquet_file: Path) -> DuckDBConnector:
    """Create a DuckDB connector with sample data."""
    DuckDBConnector.reset_instance()

    connector = DuckDBConnector(
        data_path="./data",
        memory_limit="256MB",
        threads=2,
        read_only=False,
    )

    # Register the test parquet file
    connector.register_parquet("amazon_sales", temp_parquet_file)

    yield connector

    connector.close()
    DuckDBConnector.reset_instance()


@pytest.fixture
def query_runner(duckdb_connector: DuckDBConnector) -> QueryRunner:
    """Create a QueryRunner instance with test connector."""
    return QueryRunner(
        connector=duckdb_connector,
        max_rows=1000,
        enforce_limit=True,
    )


def create_state(
    sql: str | None = None,
    sql_is_valid: bool = True,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Create a mock state dictionary for testing.

    Args:
        sql: The generated SQL query.
        sql_is_valid: Whether the SQL passed validation.
        validation_errors: List of validation errors.

    Returns:
        Mock state dictionary.
    """
    return {
        "user_query": "What are the top products?",
        "query_mode": "query",
        "generated_sql": sql,
        "sql_is_valid": sql_is_valid,
        "validation_errors": validation_errors or [],
        "retry_count": 0,
        "max_retries": 3,
        "thread_id": "test-thread",
        "messages": [],
    }


class TestSanitizeValue:
    """Tests for value sanitization."""

    def test_sanitize_none(self):
        """None values should remain None."""
        assert _sanitize_value(None) is None

    def test_sanitize_nan(self):
        """NaN should become None."""
        assert _sanitize_value(float("nan")) is None

    def test_sanitize_infinity(self):
        """Infinity should become None."""
        assert _sanitize_value(float("inf")) is None
        assert _sanitize_value(float("-inf")) is None

    def test_sanitize_normal_float(self):
        """Normal floats should remain unchanged."""
        assert _sanitize_value(3.14) == 3.14

    def test_sanitize_integer(self):
        """Integers should remain unchanged."""
        assert _sanitize_value(42) == 42

    def test_sanitize_string(self):
        """Strings should remain unchanged."""
        assert _sanitize_value("hello") == "hello"

    def test_sanitize_boolean(self):
        """Booleans should remain unchanged."""
        assert _sanitize_value(True) is True
        assert _sanitize_value(False) is False

    def test_sanitize_datetime(self):
        """Datetime should be converted to ISO format."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = _sanitize_value(dt)
        assert result == "2024-01-15T10:30:00"

    def test_sanitize_date(self):
        """Date should be converted to ISO format."""
        d = date(2024, 1, 15)
        result = _sanitize_value(d)
        assert result == "2024-01-15"

    def test_sanitize_decimal(self):
        """Decimal should be converted to float."""
        d = Decimal("3.14159")
        result = _sanitize_value(d)
        assert result == pytest.approx(3.14159)


class TestSanitizeRow:
    """Tests for row sanitization."""

    def test_sanitize_simple_row(self):
        """Simple row should have all values sanitized."""
        row = {"name": "Test", "value": 42, "active": True}
        result = _sanitize_row(row)
        assert result == {"name": "Test", "value": 42, "active": True}

    def test_sanitize_row_with_nan(self):
        """Row with NaN values should have them converted to None."""
        row = {"name": "Test", "value": float("nan"), "other": 42}
        result = _sanitize_row(row)
        assert result["name"] == "Test"
        assert result["value"] is None
        assert result["other"] == 42

    def test_sanitize_row_with_datetime(self):
        """Row with datetime should have it converted to ISO string."""
        row = {"name": "Test", "created_at": datetime(2024, 1, 15, 10, 30, 0)}
        result = _sanitize_row(row)
        assert result["created_at"] == "2024-01-15T10:30:00"


class TestErrorClassification:
    """Tests for error classification."""

    def test_classify_syntax_error(self):
        """Syntax errors should be classified correctly."""
        error = Exception("Syntax error at position 10")
        error_type, _ = _classify_error(error)
        assert error_type == DuckDBErrorType.SYNTAX_ERROR

    def test_classify_table_not_found(self):
        """Table not found errors should be classified correctly."""
        error = Exception("Table 'unknown_table' does not exist")
        error_type, _ = _classify_error(error)
        assert error_type == DuckDBErrorType.TABLE_NOT_FOUND

    def test_classify_column_not_found(self):
        """Column not found errors should be classified correctly."""
        error = Exception("Unknown column 'xyz'")
        error_type, _ = _classify_error(error)
        assert error_type == DuckDBErrorType.COLUMN_NOT_FOUND

    def test_classify_type_mismatch(self):
        """Type mismatch errors should be classified correctly."""
        error = Exception("Type mismatch in comparison")
        error_type, _ = _classify_error(error)
        assert error_type == DuckDBErrorType.TYPE_MISMATCH

    def test_classify_division_by_zero(self):
        """Division by zero should be classified correctly."""
        error = Exception("Division by zero error")
        error_type, _ = _classify_error(error)
        assert error_type == DuckDBErrorType.DIVISION_BY_ZERO

    def test_classify_unknown_error(self):
        """Unknown errors should be classified as UNKNOWN."""
        error = Exception("Some completely unknown error")
        error_type, _ = _classify_error(error)
        assert error_type == DuckDBErrorType.UNKNOWN


class TestErrorFormatting:
    """Tests for LLM-friendly error formatting."""

    def test_format_syntax_error(self):
        """Syntax errors should include helpful suggestions."""
        msg = _format_error_for_llm(DuckDBErrorType.SYNTAX_ERROR, "Missing comma")
        assert "syntax error" in msg.lower()
        assert "Missing comma" in msg

    def test_format_table_not_found(self):
        """Table not found should suggest checking available tables."""
        msg = _format_error_for_llm(
            DuckDBErrorType.TABLE_NOT_FOUND,
            "Table 'xyz' not found",
        )
        assert "table" in msg.lower()
        assert "verify" in msg.lower() or "check" in msg.lower()

    def test_format_timeout(self):
        """Timeout errors should suggest simplification."""
        msg = _format_error_for_llm(
            DuckDBErrorType.TIMEOUT,
            "Query exceeded 30s",
        )
        assert "timeout" in msg.lower() or "timed out" in msg.lower()
        assert "simplify" in msg.lower() or "filter" in msg.lower()


class TestMockExecutor:
    """Tests for the mock executor."""

    @pytest.mark.asyncio
    async def test_mock_executor_returns_data(self):
        """Mock executor should return provided mock data."""
        mock_data = [{"id": 1, "name": "Test"}]
        mock_fn = create_mock_executor(mock_data=mock_data)

        state = create_state(sql="SELECT * FROM test")
        result = await mock_fn(state)

        assert result["query_results"] == mock_data
        assert result["row_count"] == 1
        assert result["execution_error"] is None

    @pytest.mark.asyncio
    async def test_mock_executor_returns_error(self):
        """Mock executor should return error when requested."""
        mock_fn = create_mock_executor(mock_error="Test error message")

        state = create_state(sql="SELECT * FROM test")
        result = await mock_fn(state)

        assert result["query_results"] is None
        assert result["execution_error"] == "Test error message"

    @pytest.mark.asyncio
    async def test_mock_executor_no_sql(self):
        """Mock executor should handle missing SQL."""
        mock_fn = create_mock_executor()

        state = create_state(sql=None)
        result = await mock_fn(state)

        assert result["query_results"] is None
        assert "No SQL query" in result["execution_error"]


class TestExecuteQueryWithDuckDB:
    """Integration tests for execute_query with real DuckDB."""

    @pytest.mark.asyncio
    async def test_execute_simple_select(self, query_runner: QueryRunner):
        """Simple SELECT should return results."""
        state = create_state(sql="SELECT * FROM amazon_sales LIMIT 5")
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        assert result["row_count"] == 5
        assert result["execution_time_ms"] > 0
        assert result["execution_error"] is None

    @pytest.mark.asyncio
    async def test_execute_aggregation_query(self, query_runner: QueryRunner):
        """Aggregation queries should work correctly."""
        state = create_state(
            sql="""
            SELECT category, SUM(price * quantity) as total_revenue
            FROM amazon_sales
            GROUP BY category
            ORDER BY total_revenue DESC
            """,
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        assert result["row_count"] == 2  # Electronics and Accessories
        assert "category" in result["query_results"][0]

    @pytest.mark.asyncio
    async def test_execute_returns_correct_columns(
        self,
        query_runner: QueryRunner,
    ):
        """Results should include correct column names."""
        state = create_state(
            sql="SELECT product_name, price FROM amazon_sales LIMIT 1",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        row = result["query_results"][0]
        assert "product_name" in row
        assert "price" in row

    @pytest.mark.asyncio
    async def test_execute_invalid_sql_returns_error(
        self,
        query_runner: QueryRunner,
    ):
        """Invalid SQL should return an error, not crash."""
        state = create_state(
            sql="SELECT * FROM nonexistent_table",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is None
        assert result["execution_error"] is not None
        assert result["row_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_no_sql(self, query_runner: QueryRunner):
        """Missing SQL should return an error."""
        state = create_state(sql=None)
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is None
        assert "No SQL query" in result["execution_error"]

    @pytest.mark.asyncio
    async def test_execute_invalid_validation(self, query_runner: QueryRunner):
        """If SQL is marked invalid, should not execute."""
        state = create_state(
            sql="SELECT * FROM amazon_sales",
            sql_is_valid=False,
            validation_errors=["Security violation: DROP not allowed"],
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is None
        # Error message should contain the validation error
        assert (
            "DROP" in result["execution_error"] or "validation" in result["execution_error"].lower()
        )

    @pytest.mark.asyncio
    async def test_execute_date_serialization(self, query_runner: QueryRunner):
        """Date columns should be serialized as ISO strings."""
        state = create_state(
            sql="SELECT sale_date FROM amazon_sales LIMIT 1",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        sale_date = result["query_results"][0]["sale_date"]
        # Should be a string in ISO format
        assert isinstance(sale_date, str)
        assert "2024-01" in sale_date

    @pytest.mark.asyncio
    async def test_execute_null_handling(self, query_runner: QueryRunner):
        """NULL values should be serialized as None."""
        state = create_state(
            sql="SELECT CASE WHEN id = 1 THEN NULL ELSE id END as nullable_id FROM amazon_sales LIMIT 2",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        # First row should have NULL (None)
        assert result["query_results"][0]["nullable_id"] is None


class TestExecuteQueryEdgeCases:
    """Edge case tests for execute_query."""

    @pytest.mark.asyncio
    async def test_empty_result_set(self, query_runner: QueryRunner):
        """Empty result sets should be handled correctly."""
        state = create_state(
            sql="SELECT * FROM amazon_sales WHERE id > 1000",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        assert result["query_results"] == []
        assert result["row_count"] == 0
        assert result["execution_error"] is None

    @pytest.mark.asyncio
    async def test_single_row_result(self, query_runner: QueryRunner):
        """Single row results should be handled correctly."""
        state = create_state(
            sql="SELECT COUNT(*) as total FROM amazon_sales",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        assert result["row_count"] == 1
        assert result["query_results"][0]["total"] == 5

    @pytest.mark.asyncio
    async def test_large_numbers(self, query_runner: QueryRunner):
        """Large numbers should be serialized correctly."""
        state = create_state(
            sql="SELECT SUM(price * quantity * 1000000) as big_number FROM amazon_sales",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["query_results"] is not None
        big_number = result["query_results"][0]["big_number"]
        assert isinstance(big_number, (int, float))
        assert big_number > 1_000_000  # Should be a big number

    @pytest.mark.asyncio
    async def test_execution_time_is_measured(self, query_runner: QueryRunner):
        """Execution time should be measured and positive."""
        state = create_state(
            sql="SELECT * FROM amazon_sales",
        )
        result = await execute_query(state, query_runner=query_runner)

        assert result["execution_time_ms"] > 0
        # Should be reasonable (under 10 seconds for a simple query)
        assert result["execution_time_ms"] < 10000


class TestExecuteQueryConcurrency:
    """Tests for concurrent query execution."""

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, query_runner: QueryRunner):
        """Multiple concurrent queries should work correctly."""
        queries = [
            "SELECT COUNT(*) as cnt FROM amazon_sales",
            "SELECT product_name FROM amazon_sales LIMIT 1",
            "SELECT category FROM amazon_sales LIMIT 1",
        ]

        states = [create_state(sql=q) for q in queries]

        # Execute all queries concurrently
        results = await asyncio.gather(
            *[execute_query(s, query_runner=query_runner) for s in states]
        )

        # All should succeed
        for result in results:
            assert result["query_results"] is not None
            assert result["execution_error"] is None
