"""Executor agent node for running validated SQL against DuckDB.

This module executes validated SQL queries and transforms results
into a JSON-serializable format for downstream agents.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from functools import partial
from typing import TYPE_CHECKING, Any

from retail_insights.core.exceptions import ExecutionError, ValidationError
from retail_insights.engine.query_runner import QueryRunner, get_query_runner

if TYPE_CHECKING:
    from retail_insights.agents.state import RetailInsightsState

logger = logging.getLogger(__name__)

# Thread pool for async execution of synchronous DuckDB calls
_executor_pool = ThreadPoolExecutor(max_workers=4)

# Maximum rows to return for LLM token efficiency
MAX_RESULT_ROWS = 1000

# Default query timeout in seconds
DEFAULT_TIMEOUT_SECONDS = 30.0


class DuckDBErrorType(StrEnum):
    """Categorized DuckDB errors for LLM-friendly messaging."""

    SYNTAX_ERROR = "syntax_error"
    TABLE_NOT_FOUND = "table_not_found"
    COLUMN_NOT_FOUND = "column_not_found"
    TYPE_MISMATCH = "type_mismatch"
    DIVISION_BY_ZERO = "division_by_zero"
    OUT_OF_MEMORY = "out_of_memory"
    IO_ERROR = "io_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


def _classify_error(error: Exception) -> tuple[DuckDBErrorType, str]:
    """Classify a DuckDB error for appropriate handling.

    Args:
        error: The exception raised by DuckDB.

    Returns:
        Tuple of (error_type, original_message).
    """
    msg = str(error).lower()

    # Important: Order matters! Check more specific patterns first.
    # Column patterns are checked before table patterns to avoid false matches.
    checks = [
        # Division by zero - very specific
        (DuckDBErrorType.DIVISION_BY_ZERO, ["division by zero"]),
        # Memory - specific phrases
        (DuckDBErrorType.OUT_OF_MEMORY, ["out of memory", "memory limit"]),
        # Syntax errors - specific to parsing
        (DuckDBErrorType.SYNTAX_ERROR, ["syntax error", "parser error", "parse error"]),
        # Type mismatch - specific phrases
        (
            DuckDBErrorType.TYPE_MISMATCH,
            [
                "type mismatch",
                "cannot cast",
                "conversion failed",
                "type error",
            ],
        ),
        # IO errors - network/file access
        (
            DuckDBErrorType.IO_ERROR,
            [
                "i/o error",
                "could not read",
                "file not found",
                "s3",
                "http",
            ],
        ),
        # Column errors - check "column" keyword (before table)
        (
            DuckDBErrorType.COLUMN_NOT_FOUND,
            ["unknown column", "column.*not found", "column.*does not exist"],
        ),
        # Table errors - generic "table" patterns
        (
            DuckDBErrorType.TABLE_NOT_FOUND,
            [
                "table.*does not exist",
                "table.*not found",
                "no such table",
                "table with name",
            ],
        ),
    ]

    import re

    for error_type, patterns in checks:
        for pattern in patterns:
            if re.search(pattern, msg):
                return error_type, str(error)

    return DuckDBErrorType.UNKNOWN, str(error)


def _format_error_for_llm(
    error_type: DuckDBErrorType,
    original_error: str,
) -> str:
    """Format error message for LLM consumption and potential retry.

    Args:
        error_type: Classified error type.
        original_error: Original error message.

    Returns:
        LLM-friendly error message with suggestions.
    """
    templates = {
        DuckDBErrorType.SYNTAX_ERROR: (
            "SQL syntax error: {error}. "
            "Check for missing commas, unclosed quotes, or invalid keywords."
        ),
        DuckDBErrorType.TABLE_NOT_FOUND: (
            "Table not found: {error}. Verify the table name matches one from the available tables."
        ),
        DuckDBErrorType.COLUMN_NOT_FOUND: (
            "Column not found: {error}. Check that column names match the table schema."
        ),
        DuckDBErrorType.TYPE_MISMATCH: (
            "Type error: {error}. Consider using CAST() or TRY_CAST() for type conversions."
        ),
        DuckDBErrorType.DIVISION_BY_ZERO: (
            "Division by zero error: {error}. Add a check for zero values in the denominator."
        ),
        DuckDBErrorType.OUT_OF_MEMORY: (
            "Query too resource-intensive: {error}. "
            "Add more restrictive WHERE filters or reduce LIMIT."
        ),
        DuckDBErrorType.IO_ERROR: (
            "Data access error: {error}. There may be an issue accessing the data source."
        ),
        DuckDBErrorType.TIMEOUT: (
            "Query timed out: {error}. "
            "Simplify the query or add more filters to reduce execution time."
        ),
    }

    template = templates.get(error_type, "Query execution failed: {error}")
    return template.format(error=original_error)


def _sanitize_value(value: Any) -> Any:
    """Convert non-JSON-serializable values to safe representations.

    Handles NaN, NaT, numpy types, datetime, and Decimal.

    Args:
        value: Any value from query results.

    Returns:
        JSON-serializable value.
    """
    if value is None:
        return None

    # Handle NaN/infinity for floats
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    # Handle numpy scalar types
    if hasattr(value, "item"):
        return value.item()

    # Handle datetime types
    if hasattr(value, "isoformat"):
        return value.isoformat()

    # Handle Decimal
    if hasattr(value, "__float__") and not isinstance(value, (int, float, bool)):
        return float(value)

    return value


def _sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Sanitize all values in a result row for JSON serialization.

    Args:
        row: Dictionary representing a result row.

    Returns:
        Sanitized dictionary safe for JSON serialization.
    """
    return {key: _sanitize_value(value) for key, value in row.items()}


def _execute_sync(
    sql: str,
    runner: QueryRunner,
) -> dict[str, Any]:
    """Execute query synchronously (runs in thread pool).

    Args:
        sql: SQL query to execute.
        runner: QueryRunner instance.

    Returns:
        Dictionary with execution results.
    """
    result = runner.execute(sql, skip_validation=True)  # Already validated

    # Sanitize data for JSON serialization
    sanitized_data = [_sanitize_row(row) for row in result.data]

    return {
        "success": result.success,
        "data": sanitized_data,
        "columns": result.columns,
        "row_count": result.row_count,
        "execution_time_ms": result.execution_time_ms,
    }


async def execute_query(
    state: RetailInsightsState,
    query_runner: QueryRunner | None = None,
) -> dict[str, Any]:
    """Execute validated SQL against DuckDB.

    This is the main executor agent node. It:
    1. Verifies SQL was validated successfully
    2. Executes the query using QueryRunner
    3. Formats results for downstream agents
    4. Handles errors gracefully

    Args:
        state: Current workflow state containing validated SQL.
        query_runner: Optional QueryRunner instance for testing.
            If not provided, uses the default singleton.

    Returns:
        Partial state update with query results or error information.
    """
    sql = state.get("generated_sql")

    # Guard: No SQL to execute
    if not sql:
        logger.warning("Executor called without generated SQL")
        return {
            "query_results": None,
            "row_count": 0,
            "execution_time_ms": 0.0,
            "execution_error": "No SQL query to execute",
        }

    # Guard: SQL not validated
    if not state.get("sql_is_valid"):
        logger.warning("Executor called with invalid SQL")
        errors = state.get("validation_errors", [])
        error_msg = "; ".join(errors) if errors else "SQL validation failed"
        return {
            "query_results": None,
            "row_count": 0,
            "execution_time_ms": 0.0,
            "execution_error": error_msg,
        }

    logger.info("Executing SQL query", extra={"sql_length": len(sql)})

    start_time = time.perf_counter()

    try:
        # Get configured query runner (use provided or default)
        runner = query_runner or get_query_runner(max_rows=MAX_RESULT_ROWS)

        # When query_runner is injected (testing), run synchronously to
        # avoid thread-local connection issues with in-memory DuckDB.
        # In production (no injected runner), use thread pool for async.
        if query_runner is not None:
            # Synchronous execution for testing
            result = _execute_sync(sql, runner)
        else:
            # Async execution via thread pool for production
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor_pool,
                    partial(_execute_sync, sql, runner),
                ),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )

        execution_time_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "Query executed successfully",
            extra={
                "row_count": result["row_count"],
                "execution_time_ms": execution_time_ms,
            },
        )

        return {
            "query_results": result["data"],
            "row_count": result["row_count"],
            "execution_time_ms": execution_time_ms,
            "execution_error": None,
        }

    except TimeoutError:
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        error_msg = _format_error_for_llm(
            DuckDBErrorType.TIMEOUT,
            f"Query exceeded {DEFAULT_TIMEOUT_SECONDS}s timeout",
        )
        logger.error("Query timed out", extra={"sql": sql[:100]})

        return {
            "query_results": None,
            "row_count": 0,
            "execution_time_ms": execution_time_ms,
            "execution_error": error_msg,
            # Set invalid for potential retry routing
            "sql_is_valid": False,
            "validation_errors": [error_msg],
        }

    except (ExecutionError, ValidationError) as e:
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        error_type, original = _classify_error(e)
        error_msg = _format_error_for_llm(error_type, str(e))

        logger.error(
            "Query execution failed",
            extra={
                "error_type": error_type.value,
                "error": str(e),
            },
        )

        return {
            "query_results": None,
            "row_count": 0,
            "execution_time_ms": execution_time_ms,
            "execution_error": error_msg,
            # Set invalid for potential retry routing
            "sql_is_valid": False,
            "validation_errors": [error_msg],
        }

    except Exception as e:
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        error_type, original = _classify_error(e)
        error_msg = _format_error_for_llm(error_type, str(e))

        logger.exception(
            "Unexpected error during query execution",
            extra={"sql": sql[:100]},
        )

        return {
            "query_results": None,
            "row_count": 0,
            "execution_time_ms": execution_time_ms,
            "execution_error": error_msg,
        }


def create_mock_executor(
    mock_data: list[dict[str, Any]] | None = None,
    mock_error: str | None = None,
    execution_time_ms: float = 50.0,
) -> callable:
    """Create a mock executor for testing.

    Args:
        mock_data: Data to return from mock execution.
        mock_error: Error message to return (if simulating failure).
        execution_time_ms: Simulated execution time.

    Returns:
        Mock executor function with same signature as execute_query.
    """

    async def mock_execute_query(state: RetailInsightsState) -> dict[str, Any]:
        """Mock implementation of execute_query for testing."""
        sql = state.get("generated_sql")

        if not sql:
            return {
                "query_results": None,
                "row_count": 0,
                "execution_time_ms": 0.0,
                "execution_error": "No SQL query to execute",
            }

        if mock_error:
            return {
                "query_results": None,
                "row_count": 0,
                "execution_time_ms": execution_time_ms,
                "execution_error": mock_error,
                "sql_is_valid": False,
                "validation_errors": [mock_error],
            }

        data = mock_data or []
        return {
            "query_results": data,
            "row_count": len(data),
            "execution_time_ms": execution_time_ms,
            "execution_error": None,
        }

    return mock_execute_query
