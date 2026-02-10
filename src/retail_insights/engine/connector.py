"""DuckDB database connector with S3/httpfs support.

This module provides a thread-safe DuckDB connection manager
with configuration for S3 Parquet access and memory limits.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from collections.abc import Generator

    from retail_insights.core.config import Settings

logger = logging.getLogger(__name__)


class DuckDBConnector:
    """Thread-safe DuckDB connection manager with S3 support.

    Provides connection pooling, S3 httpfs configuration,
    and memory/thread limit enforcement.

    Attributes:
        data_path: Path to local data directory.
        memory_limit: DuckDB memory limit string (e.g., "1GB").
        threads: Number of DuckDB worker threads.
        read_only: Whether connections are read-only.
    """

    _instance: DuckDBConnector | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        settings: Settings | None = None,
        data_path: str | Path | None = None,
        memory_limit: str | None = None,
        threads: int | None = None,
        read_only: bool = True,
    ) -> None:
        """Initialize DuckDB connector.

        Args:
            settings: Optional Settings instance for configuration.
            data_path: Path to local data directory (overrides settings).
            memory_limit: DuckDB memory limit (overrides settings).
            threads: Number of worker threads (overrides settings).
            read_only: Whether to enforce read-only mode.
        """
        if settings:
            self.data_path = Path(data_path or settings.LOCAL_DATA_PATH)
            self.memory_limit = memory_limit or settings.DUCKDB_MEMORY_LIMIT
            self.threads = threads or settings.DUCKDB_THREADS
            self._s3_bucket = settings.AWS_S3_BUCKET
            self._s3_region = settings.AWS_REGION
            self._aws_access_key = settings.AWS_ACCESS_KEY_ID
            self._aws_secret_key = (
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            )
        else:
            self.data_path = Path(data_path or "./data")
            self.memory_limit = memory_limit or "1GB"
            self.threads = threads or 4
            self._s3_bucket = None
            self._s3_region = "us-east-1"
            self._aws_access_key = None
            self._aws_secret_key = None

        self.read_only = read_only
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._local = threading.local()

        logger.info(
            "DuckDB connector initialized",
            extra={
                "data_path": str(self.data_path),
                "memory_limit": self.memory_limit,
                "threads": self.threads,
                "read_only": self.read_only,
                "s3_configured": self._s3_bucket is not None,
            },
        )

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> DuckDBConnector:
        """Get or create singleton connector instance.

        Args:
            settings: Optional Settings for first initialization.

        Returns:
            DuckDBConnector: Singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(settings=settings)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None

    def _create_connection(self) -> duckdb.DuckDBPyConnection:
        """Create a new DuckDB connection with configuration.

        Returns:
            Configured DuckDB connection.
        """
        # Create in-memory database with configuration
        conn = duckdb.connect(":memory:", read_only=False)

        # Set memory and thread limits
        conn.execute(f"SET memory_limit = '{self.memory_limit}';")
        conn.execute(f"SET threads = {self.threads};")

        # Note: access_mode cannot be changed after connection is opened
        # For in-memory databases, we enforce read-only at the query validation level

        # Configure S3 httpfs if credentials provided
        if self._aws_access_key and self._aws_secret_key:
            self._configure_s3(conn)

        logger.debug("Created new DuckDB connection")
        return conn

    def _configure_s3(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Configure S3 httpfs extension.

        Args:
            conn: DuckDB connection to configure.
        """
        try:
            # Install and load httpfs extension
            conn.execute("INSTALL httpfs;")
            conn.execute("LOAD httpfs;")

            # Set S3 credentials
            conn.execute(f"SET s3_region = '{self._s3_region}';")
            conn.execute(f"SET s3_access_key_id = '{self._aws_access_key}';")
            conn.execute(f"SET s3_secret_access_key = '{self._aws_secret_key}';")

            logger.debug("S3 httpfs configured successfully")
        except duckdb.Error as e:
            logger.warning(f"Failed to configure S3 httpfs: {e}")

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get the shared DuckDB connection.

        Uses a single shared connection for in-memory databases so that
        registered views are accessible across all operations.

        Returns:
            Shared DuckDB connection.
        """
        if self._connection is None:
            with self._lock:
                if self._connection is None:
                    self._connection = self._create_connection()
        return self._connection

    @contextmanager
    def connection(self) -> Generator[duckdb.DuckDBPyConnection]:
        """Context manager for database connection.

        Yields:
            DuckDB connection for use within context.

        Example:
            with connector.connection() as conn:
                result = conn.execute("SELECT 1").fetchall()
        """
        conn = self.get_connection()
        try:
            yield conn
        finally:
            # Connection remains open for reuse
            pass

    def execute(
        self,
        query: str,
        parameters: tuple | list | dict | None = None,
    ) -> duckdb.DuckDBPyConnection:
        """Execute a query and return result relation.

        Args:
            query: SQL query to execute.
            parameters: Optional query parameters.

        Returns:
            DuckDB connection with executed query result.
        """
        conn = self.get_connection()
        if parameters:
            return conn.execute(query, parameters)
        return conn.execute(query)

    def execute_fetchall(
        self,
        query: str,
        parameters: tuple | list | dict | None = None,
    ) -> list[tuple]:
        """Execute a query and fetch all results.

        Args:
            query: SQL query to execute.
            parameters: Optional query parameters.

        Returns:
            List of result tuples.
        """
        result = self.execute(query, parameters)
        return result.fetchall()

    def execute_fetchdf(
        self,
        query: str,
        parameters: tuple | list | dict | None = None,
    ):
        """Execute a query and return as pandas DataFrame.

        Args:
            query: SQL query to execute.
            parameters: Optional query parameters.

        Returns:
            pandas DataFrame with query results.
        """
        result = self.execute(query, parameters)
        return result.fetchdf()

    def register_parquet(
        self,
        table_name: str,
        path: str | Path,
    ) -> None:
        """Register a Parquet file as a named table.

        Args:
            table_name: Name to register the table as.
            path: Path to Parquet file or S3 URI.
        """
        conn = self.get_connection()
        path_str = str(path)

        # Support glob patterns for partitioned data
        sql = f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM read_parquet('{path_str}')"  # nosec B608
        conn.execute(sql)

        logger.info(f"Registered Parquet table: {table_name} from {path_str}")

    def register_local_parquet(self, table_name: str, filename: str) -> None:
        """Register a local Parquet file from the data directory.

        Args:
            table_name: Name to register the table as.
            filename: Filename within data_path directory.
        """
        path = self.data_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}")
        self.register_parquet(table_name, path)

    def register_s3_parquet(self, table_name: str, s3_key: str) -> None:
        """Register an S3 Parquet file as a named table.

        Args:
            table_name: Name to register the table as.
            s3_key: S3 key (path within bucket).

        Raises:
            ValueError: If S3 bucket not configured.
        """
        if not self._s3_bucket:
            raise ValueError("S3 bucket not configured")

        s3_uri = f"s3://{self._s3_bucket}/{s3_key}"
        self.register_parquet(table_name, s3_uri)

    def list_tables(self) -> list[str]:
        """List all registered tables and views.

        Returns:
            List of table/view names.
        """
        result = self.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        )
        return [row[0] for row in result.fetchall()]

    def get_table_schema(self, table_name: str) -> list[dict[str, str]]:
        """Get schema information for a table.

        Args:
            table_name: Name of the table.

        Returns:
            List of column info dicts with 'name', 'type', 'nullable'.
        """
        result = self.execute(f"DESCRIBE {table_name}")
        columns = []
        for row in result.fetchall():
            columns.append(
                {
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES" if len(row) > 2 else True,
                }
            )
        return columns

    def close(self) -> None:
        """Close the main connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        logger.debug("DuckDB connector closed")

    def __enter__(self) -> DuckDBConnector:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
