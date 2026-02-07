"""Pydantic models for API requests, responses, and agent I/O."""

from retail_insights.models.agents import (
    RouterDecision,
    SQLGenerationResult,
    ValidationResult,
)
from retail_insights.models.requests import QueryRequest, SummarizeRequest
from retail_insights.models.responses import (
    ErrorResponse,
    QueryResult,
    SummaryResult,
)
from retail_insights.models.schema import (
    ColumnSchema,
    DataSource,
    SchemaRegistryState,
    TableSchema,
)

__all__ = [
    # Request/Response models
    "QueryRequest",
    "SummarizeRequest",
    "QueryResult",
    "SummaryResult",
    "ErrorResponse",
    # Agent models
    "RouterDecision",
    "SQLGenerationResult",
    "ValidationResult",
    # Schema models
    "ColumnSchema",
    "TableSchema",
    "DataSource",
    "SchemaRegistryState",
]
