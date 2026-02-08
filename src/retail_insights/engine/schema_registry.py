"""Schema Registry for dynamic table discovery and caching.

This module provides the SchemaRegistry class that discovers table schemas
from S3 Parquet files, local files, and PostgreSQL databases with TTL caching.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from cachetools import TTLCache

from retail_insights.models.schema import (
    ColumnSchema,
    DataSource,
    SchemaRegistryState,
    TableSchema,
)

if TYPE_CHECKING:
    from retail_insights.core.config import Settings
    from retail_insights.engine.connector import DuckDBConnector

logger = logging.getLogger(__name__)

# Default cache settings
DEFAULT_CACHE_TTL = 300  # 5 minutes
DEFAULT_CACHE_SIZE = 100


class SchemaRegistry:
    """Dynamic schema discovery and caching for multiple data sources.

    Features:
    - Auto-discovers tables from S3, local files, and PostgreSQL
    - Caches schema with configurable TTL (default 5 minutes)
    - Provides schema context for SQL Generator agent
    - Thread-safe refresh mechanism

    Attributes:
        sources: List of data sources to discover.
        cache_ttl: Cache time-to-live in seconds.
        connector: DuckDB connector for discovery queries.
    """

    _instance: SchemaRegistry | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        sources: list[DataSource] | None = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        connector: DuckDBConnector | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize schema registry.

        Args:
            sources: List of data sources to discover from.
            cache_ttl: Cache TTL in seconds (default 300 = 5 minutes).
            connector: Optional DuckDB connector (creates one if not provided).
            settings: Optional Settings for configuration.
        """
        self.cache_ttl = cache_ttl
        self._sources = sources or []
        self._connector = connector
        self._settings = settings

        # Thread-safe cache for schemas
        self._cache: TTLCache[str, TableSchema] = TTLCache(
            maxsize=DEFAULT_CACHE_SIZE,
            ttl=cache_ttl,
        )
        self._cache_lock = threading.RLock()

        # State tracking
        self._last_refresh: datetime | None = None
        self._refresh_lock = threading.Lock()
        self._initialized = False

        logger.info(
            "SchemaRegistry initialized",
            extra={"sources": len(self._sources), "cache_ttl": cache_ttl},
        )

    @classmethod
    def get_instance(
        cls,
        settings: Settings | None = None,
        sources: list[DataSource] | None = None,
    ) -> SchemaRegistry:
        """Get or create singleton registry instance.

        Args:
            settings: Optional Settings for first initialization.
            sources: Optional data sources for first initialization.

        Returns:
            SchemaRegistry: Singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(sources=sources, settings=settings)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None

    @property
    def is_stale(self) -> bool:
        """Check if cache needs refresh."""
        if self._last_refresh is None:
            return True
        elapsed = datetime.now() - self._last_refresh
        return elapsed > timedelta(seconds=self.cache_ttl)

    @property
    def connector(self) -> DuckDBConnector:
        """Get DuckDB connector, creating if needed."""
        if self._connector is None:
            from retail_insights.engine.connector import DuckDBConnector

            self._connector = DuckDBConnector.get_instance(self._settings)
        return self._connector

    def add_source(self, source: DataSource) -> None:
        """Add a data source to the registry.

        Args:
            source: Data source configuration to add.
        """
        self._sources.append(source)
        self._initialized = False  # Force re-discovery
        logger.info(f"Added data source: {source.type} - {source.path}")

    def get_state(self) -> SchemaRegistryState:
        """Get current registry state.

        Returns:
            SchemaRegistryState with current cache status.
        """
        with self._cache_lock:
            tables = dict(self._cache)

        source_stats: dict[str, int] = {}
        for table in tables.values():
            source_stats[table.source_type] = source_stats.get(table.source_type, 0) + 1

        return SchemaRegistryState(
            tables=tables,
            last_refresh=self._last_refresh,
            source_stats=source_stats,
            is_stale=self.is_stale,
        )

    def get_schema(self, force_refresh: bool = False) -> dict[str, TableSchema]:
        """Get cached schema, refreshing if stale.

        Args:
            force_refresh: If True, refresh even if cache is valid.

        Returns:
            Dict of table_name -> TableSchema.
        """
        if force_refresh or self.is_stale:
            self.refresh_schema()

        with self._cache_lock:
            return dict(self._cache)

    def get_table(self, table_name: str) -> TableSchema | None:
        """Get schema for a specific table.

        Args:
            table_name: Name of the table (case-insensitive).

        Returns:
            TableSchema if found, None otherwise.
        """
        if self.is_stale:
            self.refresh_schema()

        with self._cache_lock:
            # Try exact match first
            if table_name in self._cache:
                return self._cache[table_name]
            # Try case-insensitive match
            for name, schema in self._cache.items():
                if name.lower() == table_name.lower():
                    return schema
        return None

    def refresh_schema(self) -> SchemaRegistryState:
        """Discover and cache schema from all sources.

        Returns:
            SchemaRegistryState with refreshed data.
        """
        with self._refresh_lock:
            logger.info("Starting schema refresh")
            new_schemas: dict[str, TableSchema] = {}

            for source in self._sources:
                if not source.enabled:
                    continue

                try:
                    if source.type == "s3":
                        tables = self._discover_s3_parquet(source)
                    elif source.type == "local":
                        tables = self._discover_local_files(source)
                    elif source.type == "postgres":
                        tables = self._discover_pg_tables(source)
                    else:
                        logger.warning(f"Unknown source type: {source.type}")
                        continue

                    new_schemas.update(tables)
                    logger.info(
                        f"Discovered {len(tables)} tables from {source.type}",
                        extra={"source_path": source.path},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to discover from {source.type}: {e}",
                        extra={"source_path": source.path},
                    )

            # Update cache atomically
            with self._cache_lock:
                self._cache.clear()
                for name, schema in new_schemas.items():
                    self._cache[name] = schema

            self._last_refresh = datetime.now()
            self._initialized = True

            logger.info(f"Schema refresh complete: {len(new_schemas)} tables discovered")
            return self.get_state()

    def _discover_s3_parquet(self, source: DataSource) -> dict[str, TableSchema]:
        """Discover Parquet files in S3 bucket.

        Args:
            source: S3 data source configuration.

        Returns:
            Dict of table_name -> TableSchema.
        """
        schemas: dict[str, TableSchema] = {}
        conn = self.connector.get_connection()

        # Build glob path
        base_path = source.path.rstrip("/")
        glob_path = f"{base_path}/{source.file_pattern}"

        try:
            # Use read_parquet with filename to discover files
            # DuckDB httpfs handles S3 credentials from environment
            files_result = conn.execute(
                f"SELECT DISTINCT filename FROM read_parquet('{glob_path}', filename=true) LIMIT 1"  # nosec B608
            ).fetchall()

            # If we can read files, get schema from first file
            if files_result:
                # Get schema without loading all data
                schema_result = conn.execute(
                    f"SELECT * FROM parquet_schema('{glob_path}')"  # nosec B608
                ).fetchall()

                # Group columns by file (for now, assume single table per glob)
                columns = self._parse_parquet_schema(schema_result)

                table_name = Path(source.path).stem or "s3_data"
                schemas[table_name] = TableSchema(
                    name=table_name,
                    source_type="s3",
                    source_path=glob_path,
                    columns=columns,
                    file_format="parquet",
                )

        except Exception as e:
            logger.warning(f"S3 Parquet discovery failed for {glob_path}: {e}")

        return schemas

    def _discover_local_files(self, source: DataSource) -> dict[str, TableSchema]:
        """Discover Parquet/CSV files from local filesystem.

        Args:
            source: Local data source configuration.

        Returns:
            Dict of table_name -> TableSchema.
        """
        schemas: dict[str, TableSchema] = {}
        base_path = Path(source.path)

        if not base_path.exists():
            logger.warning(f"Local path does not exist: {base_path}")
            return schemas

        conn = self.connector.get_connection()

        # Find all matching files
        for file_path in base_path.glob(source.file_pattern):
            if file_path.is_dir():
                continue

            table_name = file_path.stem

            # Determine read function based on extension
            suffix = file_path.suffix.lower()
            if suffix == ".parquet":
                read_func = "read_parquet"
                file_format = "parquet"
            elif suffix == ".csv":
                read_func = "read_csv_auto"
                file_format = "csv"
            else:
                continue

            try:
                # Get schema using DESCRIBE
                path_str = str(file_path).replace("\\", "/")
                result = conn.execute(
                    f"DESCRIBE SELECT * FROM {read_func}('{path_str}')"  # nosec B608
                ).fetchall()

                columns = [
                    ColumnSchema(
                        name=row[0],
                        data_type=row[1],
                        nullable=row[2] == "YES" if len(row) > 2 else True,
                    )
                    for row in result
                ]

                # Get sample values for first few columns
                columns = self._add_sample_values(conn, columns, read_func, path_str)

                # Get row count estimate
                count_result = conn.execute(
                    f"SELECT COUNT(*) FROM {read_func}('{path_str}')"  # nosec B608
                ).fetchone()
                row_count = count_result[0] if count_result else None

                schemas[table_name] = TableSchema(
                    name=table_name,
                    source_type="local",
                    source_path=path_str,
                    columns=columns,
                    row_count=row_count,
                    last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
                    file_format=file_format,
                )

            except Exception as e:
                logger.warning(f"Failed to describe {file_path}: {e}")

        return schemas

    def _discover_pg_tables(self, source: DataSource) -> dict[str, TableSchema]:
        """Discover tables from PostgreSQL database.

        Args:
            source: PostgreSQL data source configuration.

        Returns:
            Dict of table_name -> TableSchema.
        """
        schemas: dict[str, TableSchema] = {}

        try:
            import psycopg

            with psycopg.connect(source.path) as conn, conn.cursor() as cur:
                # Query information_schema for tables
                cur.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_type = 'BASE TABLE'
                    """)
                tables = cur.fetchall()

                for (table_name,) in tables:
                    # Get columns
                    cur.execute(
                        """
                            SELECT column_name, data_type, is_nullable
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                            AND table_name = %s
                            ORDER BY ordinal_position
                        """,
                        (table_name,),
                    )
                    cols = cur.fetchall()

                    columns = [
                        ColumnSchema(
                            name=col[0],
                            data_type=col[1],
                            nullable=col[2] == "YES",
                        )
                        for col in cols
                    ]

                    schemas[table_name] = TableSchema(
                        name=table_name,
                        source_type="postgres",
                        source_path=f"{source.path}/{table_name}",
                        columns=columns,
                    )

        except ImportError:
            logger.warning("psycopg not installed, skipping PostgreSQL discovery")
        except Exception as e:
            logger.error(f"PostgreSQL discovery failed: {e}")

        return schemas

    def _parse_parquet_schema(self, schema_result: list[tuple]) -> list[ColumnSchema]:
        """Parse DuckDB parquet_schema() result into ColumnSchema list.

        Args:
            schema_result: Result from parquet_schema() query.

        Returns:
            List of ColumnSchema objects.
        """
        columns = []
        for row in schema_result:
            # parquet_schema returns: file_name, name, type, ...
            if len(row) >= 3:
                columns.append(
                    ColumnSchema(
                        name=row[1],
                        data_type=row[2],
                        nullable=True,  # Parquet schema doesn't include nullable
                    )
                )
        return columns

    def _add_sample_values(
        self,
        conn,
        columns: list[ColumnSchema],
        read_func: str,
        path: str,
        sample_limit: int = 3,
    ) -> list[ColumnSchema]:
        """Add sample values to columns for LLM context.

        Args:
            conn: DuckDB connection.
            columns: List of columns to add samples to.
            read_func: DuckDB read function name.
            path: Path to the file.
            sample_limit: Max samples per column.

        Returns:
            Updated list of columns with sample values.
        """
        # Only sample first few columns to limit query size
        sample_cols = columns[:5]
        col_names = [col.name for col in sample_cols]

        if not col_names:
            return columns

        try:
            select_clause = ", ".join(
                [f"DISTINCT CAST({name} AS VARCHAR) as {name}" for name in col_names]
            )
            result = conn.execute(
                f"SELECT {select_clause} FROM {read_func}('{path}') LIMIT 10"  # nosec B608
            ).fetchdf()

            for col in columns:
                if col.name in result.columns:
                    samples = result[col.name].dropna().unique().tolist()[:sample_limit]
                    col.sample_values = [str(v) for v in samples]

        except Exception as e:
            logger.debug(f"Failed to get sample values: {e}")

        return columns

    def get_valid_tables(self) -> list[str]:
        """Get list of valid table names.

        Returns:
            List of table names in the registry.
        """
        if self.is_stale:
            self.refresh_schema()

        with self._cache_lock:
            return list(self._cache.keys())

    def get_valid_columns(self, table_name: str) -> list[str]:
        """Get list of valid column names for a table.

        Args:
            table_name: Name of the table.

        Returns:
            List of column names, empty if table not found.
        """
        table = self.get_table(table_name)
        if table is None:
            return []
        return table.get_column_names()

    def get_schema_context(self, max_tables: int = 20) -> str:
        """Generate schema context string for SQL Generator prompt.

        Args:
            max_tables: Maximum number of tables to include.

        Returns:
            Markdown-formatted schema documentation.
        """
        schemas = self.get_schema()

        if not schemas:
            return "No tables discovered. Please check data source configuration."

        lines = ["## Available Tables\n"]

        for i, (table_name, schema) in enumerate(schemas.items()):
            if i >= max_tables:
                lines.append(f"\n... and {len(schemas) - max_tables} more tables")
                break

            lines.append(f"### {table_name}")
            lines.append(f"Source: {schema.source_type}")
            if schema.row_count:
                lines.append(f"Rows: ~{schema.row_count:,}")
            lines.append("")
            lines.append("| Column | Type | Samples |")
            lines.append("|--------|------|---------|")

            for col in schema.columns:
                samples = ", ".join(col.sample_values[:3]) if col.sample_values else "-"
                lines.append(f"| {col.name} | {col.data_type} | {samples} |")

            lines.append("")

        return "\n".join(lines)


# Module-level convenience functions
_registry: SchemaRegistry | None = None


def get_schema_registry(settings: Settings | None = None) -> SchemaRegistry:
    """Get or create the schema registry singleton.

    Args:
        settings: Optional settings for first initialization.

    Returns:
        SchemaRegistry singleton instance.
    """
    return SchemaRegistry.get_instance(settings=settings)


def get_valid_tables() -> list[str]:
    """Convenience function for validator agent.

    Returns:
        List of valid table names.
    """
    return get_schema_registry().get_valid_tables()


def get_valid_columns(table_name: str) -> list[str]:
    """Convenience function for validator agent.

    Args:
        table_name: Name of the table.

    Returns:
        List of valid column names.
    """
    return get_schema_registry().get_valid_columns(table_name)


def get_schema_context() -> str:
    """Convenience function for SQL Generator agent.

    Returns:
        Markdown-formatted schema context.
    """
    return get_schema_registry().get_schema_context()
