"""Query runner for executing validated SQL against DuckDB.

This module provides safe query execution with table name rewriting,
query validation, and result transformation.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from retail_insights.core.exceptions import ExecutionError, ValidationError
from retail_insights.engine.connector import DuckDBConnector
from retail_insights.models.agents import ExecutionResult

if TYPE_CHECKING:
    import pandas as pd

    from retail_insights.core.config import Settings

logger = logging.getLogger(__name__)


# SQL keywords that indicate write operations (blocked in read-only mode)
WRITE_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "REPLACE",
        "MERGE",
        "GRANT",
        "REVOKE",
    }
)

# Maximum rows to return by default
DEFAULT_MAX_ROWS = 1000


@dataclass
class TableMapping:
    """Mapping from logical table name to physical path.

    Attributes:
        logical_name: Table name used in SQL queries.
        physical_path: Actual path (local file or S3 URI).
        source_type: Type of source ('local', 's3', 'view').
    """

    logical_name: str
    physical_path: str
    source_type: str = "local"


class QueryRunner:
    """Executes validated SQL queries against DuckDB.

    Provides table name rewriting, SQL safety validation,
    LIMIT enforcement, and result transformation.

    Attributes:
        connector: DuckDB connector instance.
        table_mappings: Dictionary of logical to physical table mappings.
        max_rows: Maximum rows to return per query.
        enforce_limit: Whether to auto-add LIMIT clause.
    """

    def __init__(
        self,
        connector: DuckDBConnector | None = None,
        settings: Settings | None = None,
        max_rows: int = DEFAULT_MAX_ROWS,
        enforce_limit: bool = True,
    ) -> None:
        """Initialize query runner.

        Args:
            connector: DuckDB connector (uses singleton if not provided).
            settings: Settings instance for configuration.
            max_rows: Maximum rows to return.
            enforce_limit: Whether to enforce LIMIT clause.
        """
        self.connector = connector or DuckDBConnector.get_instance(settings)
        self.table_mappings: dict[str, TableMapping] = {}
        self.max_rows = max_rows
        self.enforce_limit = enforce_limit

        logger.info(
            "QueryRunner initialized",
            extra={"max_rows": max_rows, "enforce_limit": enforce_limit},
        )

    def register_table(
        self,
        logical_name: str,
        physical_path: str,
        source_type: str = "local",
    ) -> None:
        """Register a table mapping.

        Args:
            logical_name: Table name used in SQL queries.
            physical_path: Actual file path or S3 URI.
            source_type: Type of source ('local', 's3', 'view').
        """
        self.table_mappings[logical_name.lower()] = TableMapping(
            logical_name=logical_name,
            physical_path=physical_path,
            source_type=source_type,
        )

        # Register with DuckDB
        self.connector.register_parquet(logical_name, physical_path)
        logger.debug(f"Registered table: {logical_name} -> {physical_path}")

    def register_tables_from_schema(
        self,
        tables: dict[str, str],
        source_type: str = "local",
    ) -> None:
        """Register multiple tables from a schema dictionary.

        Args:
            tables: Dictionary mapping logical names to physical paths.
            source_type: Type of source for all tables.
        """
        for logical_name, physical_path in tables.items():
            self.register_table(logical_name, physical_path, source_type)

    def validate_sql(self, sql: str) -> tuple[bool, list[str]]:
        """Validate SQL query for safety.

        Args:
            sql: SQL query to validate.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors = []
        sql_upper = sql.upper().strip()

        # Check for write operations
        first_word = sql_upper.split()[0] if sql_upper.split() else ""
        if first_word in WRITE_KEYWORDS:
            errors.append(f"Write operation not allowed: {first_word}")

        # Check for dangerous patterns
        dangerous_patterns = [
            (r";\s*\w", "Multiple statements not allowed"),
            (r"--", "SQL comments not allowed"),
            (r"/\*", "SQL block comments not allowed"),
        ]

        for pattern, message in dangerous_patterns:
            if re.search(pattern, sql):
                errors.append(message)

        # Validate it starts with SELECT or WITH (common patterns)
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            errors.append("Query must start with SELECT or WITH")

        return len(errors) == 0, errors

    def rewrite_table_names(self, sql: str) -> str:
        """Rewrite logical table names to physical paths if needed.

        This method handles cases where SQL references logical table
        names that need to be expanded to read_parquet() calls.

        Args:
            sql: Original SQL query.

        Returns:
            Rewritten SQL with table references resolved.
        """
        # For tables already registered as views, no rewriting needed
        # This is a placeholder for more complex rewriting logic
        return sql

    def _ensure_limit(self, sql: str) -> str:
        """Ensure query has a LIMIT clause.

        Args:
            sql: SQL query.

        Returns:
            SQL with LIMIT clause added if missing.
        """
        if not self.enforce_limit:
            return sql

        sql_upper = sql.upper().strip()

        # Check if LIMIT clause already exists (not inside subquery)
        # Use regex to find LIMIT keyword followed by number
        # This avoids false positives from table names containing "LIMIT"
        limit_pattern = r"\bLIMIT\s+\d+"

        # Simple heuristic: check if LIMIT clause appears after last )
        last_paren = sql_upper.rfind(")")
        after_parens = sql_upper[last_paren + 1 :] if last_paren >= 0 else sql_upper

        if not re.search(limit_pattern, after_parens):
            # Remove trailing semicolon if present
            sql = sql.rstrip().rstrip(";")
            sql = f"{sql} LIMIT {self.max_rows}"

        return sql

    def execute(
        self,
        sql: str,
        skip_validation: bool = False,
    ) -> ExecutionResult:
        """Execute a SQL query and return structured result.

        Args:
            sql: SQL query to execute.
            skip_validation: Skip safety validation (use with caution).

        Returns:
            ExecutionResult with data or error information.
        """
        start_time = time.perf_counter()

        # Validate SQL
        if not skip_validation:
            is_valid, errors = self.validate_sql(sql)
            if not is_valid:
                raise ValidationError(
                    message=f"SQL validation failed: {'; '.join(errors)}",
                    errors=errors,
                    sql=sql,
                )

        # Rewrite table names if needed
        rewritten_sql = self.rewrite_table_names(sql)

        # Ensure LIMIT clause
        final_sql = self._ensure_limit(rewritten_sql)

        try:
            # Execute query
            result = self.connector.execute_fetchall(final_sql)

            # Get column names from cursor description
            conn = self.connector.get_connection()
            description = conn.description

            columns = [desc[0] for desc in description] if description else []

            # Convert to list of dicts
            data = [dict(zip(columns, row, strict=False)) for row in result]

            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "Query executed successfully",
                extra={
                    "row_count": len(data),
                    "execution_time_ms": execution_time_ms,
                },
            )

            return ExecutionResult(
                success=True,
                data=data,
                row_count=len(data),
                columns=columns,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            error_msg = str(e)
            logger.error(f"Query execution failed: {error_msg}")

            raise ExecutionError(
                message="Query execution failed",
                sql=final_sql,
                original_error=error_msg,
            ) from e

    def execute_to_df(
        self,
        sql: str,
        skip_validation: bool = False,
    ) -> pd.DataFrame:
        """Execute a SQL query and return as DataFrame.

        Args:
            sql: SQL query to execute.
            skip_validation: Skip safety validation.

        Returns:
            pandas DataFrame with query results.
        """
        if not skip_validation:
            is_valid, errors = self.validate_sql(sql)
            if not is_valid:
                raise ValidationError(
                    message=f"SQL validation failed: {'; '.join(errors)}",
                    errors=errors,
                    sql=sql,
                )

        rewritten_sql = self.rewrite_table_names(sql)
        final_sql = self._ensure_limit(rewritten_sql)

        return self.connector.execute_fetchdf(final_sql)

    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a registered table.

        Args:
            table_name: Logical table name.

        Returns:
            Dictionary with table information.
        """
        mapping = self.table_mappings.get(table_name.lower())

        if mapping:
            schema = self.connector.get_table_schema(mapping.logical_name)
            return {
                "logical_name": mapping.logical_name,
                "physical_path": mapping.physical_path,
                "source_type": mapping.source_type,
                "columns": schema,
            }
        else:
            # Try to get schema directly (might be a DuckDB-registered table)
            try:
                schema = self.connector.get_table_schema(table_name)
                return {
                    "logical_name": table_name,
                    "physical_path": None,
                    "source_type": "unknown",
                    "columns": schema,
                }
            except Exception as e:
                raise ValueError(f"Table not found: {table_name}") from e

    def list_available_tables(self) -> list[str]:
        """List all available tables.

        Returns:
            List of registered table names.
        """
        return self.connector.list_tables()


def get_query_runner(
    settings: Settings | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> QueryRunner:
    """Get a configured QueryRunner instance.

    Args:
        settings: Optional Settings for configuration.
        max_rows: Maximum rows per query.

    Returns:
        Configured QueryRunner instance.
    """
    connector = DuckDBConnector.get_instance(settings)
    return QueryRunner(connector=connector, max_rows=max_rows)
