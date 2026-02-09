"""API request models for the Retail Insights Assistant.

This module defines Pydantic models for all incoming API requests.
"""

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

SQL_INJECTION_PATTERNS = [
    r"(?i)(--|#|;)\s*$",
    r"(?i)\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE)\b.*\bTABLE\b",
    r"(?i)\b(UNION\s+ALL|UNION\s+SELECT)\b",
    r"(?i)\bEXEC\s*\(",
    r"(?i)\b(xp_|sp_)\w+",
    r"(?i)1\s*=\s*1|'\s*OR\s*'1'\s*=\s*'1",
    r"(?i)WAITFOR\s+DELAY",
    r"(?i)BENCHMARK\s*\(",
    r"(?i)SLEEP\s*\(",
]

XSS_PATTERNS = [
    r"<\s*script",
    r"javascript\s*:",
    r"on\w+\s*=",
    r"<\s*iframe",
    r"<\s*object",
    r"<\s*embed",
    r"data\s*:\s*text/html",
]


def sanitize_input(value: str, field_name: str = "input") -> str:
    """Validate input for potential injection patterns.

    Args:
        value: Input string to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated string.

    Raises:
        ValueError: If suspicious patterns are detected.
    """
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, value):
            raise ValueError(f"Potentially unsafe content detected in {field_name}")

    for pattern in XSS_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError(f"Potentially unsafe HTML/script content in {field_name}")

    return value


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

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        """Validate question for injection patterns."""
        return sanitize_input(v, "question")

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        """Validate session_id format."""
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("session_id must be alphanumeric with dashes/underscores")
        return v


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

    @field_validator("time_period", "region", "category")
    @classmethod
    def validate_string_fields(cls, v: str | None) -> str | None:
        """Validate string fields for injection patterns."""
        if v is None:
            return v
        return sanitize_input(v, "filter")


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
