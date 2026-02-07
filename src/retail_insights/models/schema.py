"""Schema models for table and column metadata.

This module defines Pydantic models for representing database schema
information discovered from various data sources.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ColumnSchema(BaseModel):
    """Schema for a single column.

    Attributes:
        name: Column name.
        data_type: SQL data type (e.g., VARCHAR, INTEGER, TIMESTAMP).
        nullable: Whether the column allows NULL values.
        description: Optional human-readable description.
        sample_values: Sample values for LLM context.
    """

    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="SQL data type")
    nullable: bool = Field(default=True, description="Whether column allows NULL")
    description: str | None = Field(default=None, description="Column description")
    sample_values: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Sample values for LLM context",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Category",
                "data_type": "VARCHAR",
                "nullable": False,
                "description": "Product category",
                "sample_values": ["Electronics", "Clothing", "Set"],
            }
        }
    }


class TableSchema(BaseModel):
    """Schema for a single table.

    Attributes:
        name: Table name (logical name for queries).
        source_type: Type of data source ('s3', 'local', 'postgres').
        source_path: Full path or URI to the data source.
        columns: List of column schemas.
        row_count: Approximate row count if available.
        last_modified: Last modification timestamp if available.
        file_format: File format for file-based sources.
    """

    name: str = Field(..., description="Table name")
    source_type: str = Field(
        ...,
        pattern="^(s3|local|postgres)$",
        description="Type of data source",
    )
    source_path: str = Field(..., description="Full path or URI to data source")
    columns: list[ColumnSchema] = Field(
        default_factory=list,
        description="List of column schemas",
    )
    row_count: int | None = Field(default=None, ge=0, description="Approximate row count")
    last_modified: datetime | None = Field(default=None, description="Last modification timestamp")
    file_format: str | None = Field(default=None, description="File format (parquet, csv, etc.)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "sales",
                "source_type": "local",
                "source_path": "./data/sales.parquet",
                "columns": [
                    {"name": "Order_ID", "data_type": "BIGINT", "nullable": False},
                    {"name": "Amount", "data_type": "DOUBLE", "nullable": True},
                ],
                "row_count": 128975,
                "file_format": "parquet",
            }
        }
    }

    def get_column_names(self) -> list[str]:
        """Get list of column names."""
        return [col.name for col in self.columns]

    def get_column(self, name: str) -> ColumnSchema | None:
        """Get column by name (case-insensitive)."""
        name_lower = name.lower()
        for col in self.columns:
            if col.name.lower() == name_lower:
                return col
        return None


class DataSource(BaseModel):
    """Configuration for a data source to discover.

    Attributes:
        type: Type of data source ('s3', 'local', 'postgres').
        path: Path, URI, or connection string for the source.
        file_pattern: Glob pattern for file discovery (for file-based sources).
        enabled: Whether this source is enabled for discovery.
    """

    type: str = Field(
        ...,
        pattern="^(s3|local|postgres)$",
        description="Type of data source",
    )
    path: str = Field(..., description="Path, URI, or connection string")
    file_pattern: str = Field(
        default="*.parquet",
        description="Glob pattern for file discovery",
    )
    enabled: bool = Field(default=True, description="Whether source is enabled")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "s3",
                    "path": "s3://my-bucket/data/",
                    "file_pattern": "**/*.parquet",
                },
                {
                    "type": "local",
                    "path": "./data",
                    "file_pattern": "*.parquet",
                },
                {
                    "type": "postgres",
                    "path": "postgresql://user:pass@localhost/db",
                    "file_pattern": "",  # Not used for postgres
                },
            ]
        }
    }


class SchemaRegistryState(BaseModel):
    """State of the schema registry cache.

    Attributes:
        tables: Dictionary of table name to TableSchema.
        last_refresh: Timestamp of last cache refresh.
        source_stats: Statistics per data source.
        is_stale: Whether cache needs refresh.
    """

    tables: dict[str, TableSchema] = Field(
        default_factory=dict,
        description="Discovered table schemas",
    )
    last_refresh: datetime | None = Field(
        default=None,
        description="Last refresh timestamp",
    )
    source_stats: dict[str, int] = Field(
        default_factory=dict,
        description="Table count per source type",
    )
    is_stale: bool = Field(default=True, description="Whether cache is stale")

    @property
    def table_count(self) -> int:
        """Get total number of discovered tables."""
        return len(self.tables)

    def get_tables_by_source(self, source_type: str) -> list[TableSchema]:
        """Get tables filtered by source type."""
        return [t for t in self.tables.values() if t.source_type == source_type]
