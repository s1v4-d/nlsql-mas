"""DuckDB data engine with S3/Parquet support.

This package provides DuckDB-based data access with:
- Thread-safe connection management
- S3 httpfs configuration
- Query execution with safety validation
- Table name rewriting and schema discovery
"""

from retail_insights.engine.connector import DuckDBConnector
from retail_insights.engine.query_runner import QueryRunner, get_query_runner
from retail_insights.engine.schema_registry import (
    SchemaRegistry,
    get_schema_context,
    get_schema_registry,
    get_valid_columns,
    get_valid_tables,
)

__all__ = [
    # Connection and query execution
    "DuckDBConnector",
    "QueryRunner",
    "get_query_runner",
    # Schema registry
    "SchemaRegistry",
    "get_schema_registry",
    "get_valid_tables",
    "get_valid_columns",
    "get_schema_context",
]
