"""DuckDB data engine with S3/Parquet support.

This package provides DuckDB-based data access with:
- Thread-safe connection management
- S3 httpfs configuration
- Query execution with safety validation
- Table name rewriting and schema discovery
"""

from retail_insights.engine.connector import DuckDBConnector
from retail_insights.engine.query_runner import QueryRunner, get_query_runner

__all__ = [
    "DuckDBConnector",
    "QueryRunner",
    "get_query_runner",
]
