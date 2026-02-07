"""API response models for the Retail Insights Assistant.

This module defines Pydantic models for all API responses.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QueryResult(BaseModel):
    """Structured query result returned to the user.

    Attributes:
        success: Whether the query executed successfully.
        answer: Human-readable answer to the query.
        sql_query: Generated SQL query (for debugging/transparency).
        data: Raw query results as list of records.
        row_count: Number of result rows.
        execution_time_ms: Query execution time in milliseconds.
        session_id: Session ID for this conversation.
    """

    success: bool = Field(..., description="Whether query executed successfully")
    answer: str = Field(..., description="Human-readable answer to the query")
    sql_query: str | None = Field(
        default=None,
        description="Generated SQL query (for debugging)",
    )
    data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Raw query results as list of records",
    )
    row_count: int = Field(default=0, description="Number of result rows")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")
    session_id: str | None = Field(
        default=None,
        description="Session ID for this conversation",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of the response",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "answer": "The top 5 categories by revenue in Q3 2022 were: Set ($2.1M), Kurta ($1.8M), Western Dress ($950K), Blouse ($720K), and Top ($580K).",
                    "sql_query": "SELECT Category, SUM(Amount) as revenue FROM amazon_sales WHERE ... GROUP BY Category ORDER BY revenue DESC LIMIT 5",
                    "data": [
                        {"Category": "Set", "revenue": 2100000},
                        {"Category": "kurta", "revenue": 1800000},
                    ],
                    "row_count": 5,
                    "execution_time_ms": 234.5,
                    "session_id": "abc123",
                }
            ]
        }
    }


class SummaryResult(BaseModel):
    """Structured summary result for sales data.

    Attributes:
        success: Whether the summary was generated successfully.
        summary: Human-readable summary narrative.
        key_metrics: Dictionary of key business metrics.
        trends: Optional trend analysis data.
        time_period: Time period covered by the summary.
        execution_time_ms: Summary generation time in milliseconds.
    """

    success: bool = Field(..., description="Whether summary was generated successfully")
    summary: str = Field(..., description="Human-readable summary narrative")
    key_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of key business metrics",
    )
    trends: dict[str, Any] | None = Field(
        default=None,
        description="Optional trend analysis data",
    )
    time_period: str = Field(..., description="Time period covered by the summary")
    execution_time_ms: float = Field(..., description="Summary generation time in milliseconds")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of the response",
    )


class ErrorResponse(BaseModel):
    """Standard error response for API errors.

    Attributes:
        success: Always False for error responses.
        error_code: Machine-readable error code.
        message: Human-readable error message.
        details: Optional additional error details.
        timestamp: Timestamp of the error.
    """

    success: bool = Field(default=False, description="Always False for errors")
    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional error details",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of the error",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": False,
                    "error_code": "VALIDATION_ERROR",
                    "message": "Could not generate valid SQL after 3 attempts",
                    "details": {"last_error": "Unknown column: 'revenues'"},
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """Health check response.

    Attributes:
        status: Health status ('healthy', 'degraded', 'unhealthy').
        version: Application version.
        components: Dictionary of component health statuses.
    """

    status: str = Field(..., description="Health status")
    version: str = Field(..., description="Application version")
    components: dict[str, str] = Field(
        default_factory=dict,
        description="Component health statuses",
    )


class SchemaRefreshResult(BaseModel):
    """Result of schema refresh operation.

    Attributes:
        success: Whether the refresh was successful.
        tables_discovered: Number of tables discovered.
        table_names: List of discovered table names.
        refresh_time_ms: Time taken to refresh in milliseconds.
    """

    success: bool = Field(..., description="Whether refresh was successful")
    tables_discovered: int = Field(..., description="Number of tables discovered")
    table_names: list[str] = Field(
        default_factory=list,
        description="List of discovered table names",
    )
    refresh_time_ms: float = Field(..., description="Refresh time in milliseconds")
