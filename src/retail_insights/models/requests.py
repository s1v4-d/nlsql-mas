"""API request models for the Retail Insights Assistant.

This module defines Pydantic models for all incoming API requests.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class QueryMode(StrEnum):
    """Mode for query processing."""

    QUERY = "query"
    SUMMARIZE = "summarize"


class QueryRequest(BaseModel):
    """Request for natural language query processing.

    Attributes:
        question: Natural language question about sales data.
        mode: Query mode - 'query' for Q&A, 'summarize' for summaries.
        session_id: Optional session ID for conversation continuity.
        max_results: Maximum number of result rows to return.
    """

    question: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Natural language question about sales data",
    )
    mode: QueryMode = Field(
        default=QueryMode.QUERY,
        description="Query mode: 'query' for Q&A, 'summarize' for summaries",
    )
    session_id: str | None = Field(
        default=None,
        max_length=64,
        description="Session ID for conversation continuity",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum number of result rows",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "question": "What were the top 5 categories by revenue in Q3 2022?",
                    "mode": "query",
                    "session_id": "abc123",
                    "max_results": 100,
                }
            ]
        }
    }


class SummarizeRequest(BaseModel):
    """Request for automated sales summary.

    Attributes:
        time_period: Time period for summary (e.g., 'last_month', 'last_quarter').
        region: Optional filter by region/state.
        category: Optional filter by product category.
        include_trends: Whether to include trend analysis.
    """

    time_period: str = Field(
        default="last_quarter",
        description="Time period for summary (e.g., 'last_month', 'last_quarter', 'ytd')",
    )
    region: str | None = Field(
        default=None,
        max_length=100,
        description="Filter by region/state",
    )
    category: str | None = Field(
        default=None,
        max_length=100,
        description="Filter by product category",
    )
    include_trends: bool = Field(
        default=True,
        description="Whether to include trend analysis in the summary",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "time_period": "last_quarter",
                    "region": "MAHARASHTRA",
                    "category": "Set",
                    "include_trends": True,
                }
            ]
        }
    }


class SchemaRefreshRequest(BaseModel):
    """Request to refresh the schema registry.

    Attributes:
        force: Force refresh even if cache is valid.
        source_type: Optional filter to refresh only specific source type.
    """

    force: bool = Field(
        default=True,
        description="Force refresh even if cache is valid",
    )
    source_type: str | None = Field(
        default=None,
        description="Optional filter: 's3', 'local', or 'postgres'",
    )
