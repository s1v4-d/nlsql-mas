"""SQL Validator agent node for query validation and safety checks.

This module implements the SQL Validator agent that validates generated SQL
using sqlglot parsing, schema validation, and security checks.
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import TYPE_CHECKING

import sqlglot
import structlog
from sqlglot import exp
from sqlglot.errors import ParseError

from retail_insights.agents.state import RetailInsightsState

if TYPE_CHECKING:
    from retail_insights.models.schema import TableSchema

logger = structlog.get_logger(__name__)

# Maximum retry count before giving up
MAX_RETRY_COUNT = 3

# Default and maximum LIMIT values
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

# Dangerous statement types that should be blocked
DANGEROUS_STATEMENT_TYPES = (
    exp.Drop,
    exp.Delete,
    exp.Insert,
    exp.Update,
    exp.Alter,
    exp.Create,
)

# Dangerous keywords to block (additional security check)
DANGEROUS_KEYWORDS = {
    "DROP",
    "DELETE",
    "INSERT",
    "UPDATE",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "MERGE",
    "GRANT",
    "REVOKE",
    "EXECUTE",
    "EXEC",
    "ATTACH",
    "DETACH",
    "COPY",
    "EXPORT",
}


async def validate_sql(state: RetailInsightsState) -> dict:
    """Validate generated SQL query for syntax, security, and schema compliance.

    Performs:
    1. Syntax validation with sqlglot (DuckDB dialect)
    2. SELECT-only enforcement
    3. Table/column existence validation
    4. Dangerous operation blocking
    5. LIMIT clause enforcement (auto-adds if missing)
    6. Retry count tracking

    Args:
        state: Current workflow state containing generated_sql and schema context.

    Returns:
        Dict with updates to state:
        - sql_is_valid: Whether the SQL passed validation
        - validation_errors: List of error messages for retry
        - validation_status: Status string ('valid', 'invalid', 'corrected')
        - generated_sql: Potentially corrected SQL (with LIMIT)

    Example:
        >>> state = create_initial_state("What are total sales?", "thread-1")
        >>> state["generated_sql"] = "SELECT SUM(Amount) FROM amazon_sales"
        >>> result = await validate_sql(state)
        >>> result["sql_is_valid"]  # May be False due to missing LIMIT
        >>> "LIMIT" in result["generated_sql"]
        True
    """
    sql = state.get("generated_sql")
    retry_count = state.get("retry_count", 0)

    logger.info(
        "validating_sql",
        sql_preview=sql[:200] if sql else None,
        thread_id=state["thread_id"],
        retry_count=retry_count,
    )

    # Check if we've exceeded retry limit
    if retry_count > MAX_RETRY_COUNT:
        return {
            "sql_is_valid": False,
            "validation_errors": [f"Maximum retry count ({MAX_RETRY_COUNT}) exceeded"],
            "validation_status": "failed",
        }

    # Check if SQL was generated
    if not sql:
        return {
            "sql_is_valid": False,
            "validation_errors": ["No SQL query was generated"],
            "validation_status": "invalid",
        }

    errors: list[str] = []
    warnings: list[str] = []
    corrected_sql = sql

    # 1. Parse SQL with DuckDB dialect
    try:
        ast = sqlglot.parse_one(sql, dialect="duckdb")
    except ParseError as e:
        error_msg = f"SQL syntax error: {e}"
        logger.warning("sql_parse_error", error=str(e))
        return {
            "sql_is_valid": False,
            "validation_errors": [error_msg],
            "validation_status": "invalid",
        }

    # 2. Check for dangerous statement types
    security_errors = _check_security(ast, sql)
    errors.extend(security_errors)

    # 3. Validate SELECT-only
    select_errors = _check_select_only(ast)
    errors.extend(select_errors)

    # 4. Validate tables against schema
    schema = _parse_schema_context(state.get("schema_context", ""))
    if schema:
        table_errors = _validate_tables(ast, schema)
        errors.extend(table_errors)

        # 5. Validate columns
        column_errors = _validate_columns(ast, schema)
        errors.extend(column_errors)

    # 6. Enforce LIMIT clause
    corrected_sql, limit_warnings = _enforce_limit(ast, sql)
    warnings.extend(limit_warnings)

    # Log validation result
    is_valid = len(errors) == 0
    status = "valid" if is_valid else "invalid"
    if is_valid and corrected_sql != sql:
        status = "corrected"

    logger.info(
        "sql_validation_complete",
        is_valid=is_valid,
        error_count=len(errors),
        warning_count=len(warnings),
        status=status,
    )

    result = {
        "sql_is_valid": is_valid,
        "validation_errors": errors if errors else None,
        "validation_status": status,
    }

    # Include corrected SQL if changed
    if corrected_sql != sql:
        result["generated_sql"] = corrected_sql

    return result


def _check_security(ast: exp.Expression, sql: str) -> list[str]:
    """Check for dangerous SQL operations.

    Args:
        ast: Parsed SQL AST.
        sql: Original SQL string for keyword check.

    Returns:
        List of security error messages.
    """
    errors = []

    # Check AST for dangerous statement types
    if isinstance(ast, DANGEROUS_STATEMENT_TYPES):
        errors.append(
            f"Blocked operation: {type(ast).__name__} is not allowed. "
            "Only SELECT queries are permitted."
        )

    # Additional keyword check for injection attempts
    sql_upper = sql.upper()
    for keyword in DANGEROUS_KEYWORDS:
        # Check if keyword appears as standalone word (not part of identifier)
        if f" {keyword} " in f" {sql_upper} ":
            errors.append(
                f"Blocked operation: {keyword} is not allowed. "
                "Only SELECT queries are permitted."
            )

    return errors


def _check_select_only(ast: exp.Expression) -> list[str]:
    """Ensure only SELECT statements are used.

    Args:
        ast: Parsed SQL AST.

    Returns:
        List of error messages if not SELECT.
    """
    # Valid statement types for read-only queries
    valid_types = (exp.Select, exp.Union, exp.Intersect, exp.Except)

    if isinstance(ast, valid_types):
        return []

    # Check if it's a CTE wrapping SELECT
    with_clause = ast.find(exp.With)
    if with_clause:
        # CTEs are OK if they contain SELECT
        return []

    return [
        f"Only SELECT statements are allowed. "
        f"Received: {type(ast).__name__}. "
        "Please rewrite as a SELECT query."
    ]


def _validate_tables(
    ast: exp.Expression,
    schema: dict[str, TableSchema],
) -> list[str]:
    """Validate all referenced tables exist in schema.

    Args:
        ast: Parsed SQL AST.
        schema: Dict of table_name -> TableSchema.

    Returns:
        List of error messages for unknown tables.
    """
    errors = []
    available_tables = set(schema.keys())
    available_lower = {t.lower(): t for t in available_tables}

    for table in ast.find_all(exp.Table):
        table_name = table.name
        table_lower = table_name.lower()

        if table_lower not in available_lower:
            # Find similar table names for suggestion
            suggestions = get_close_matches(
                table_lower,
                list(available_lower.keys()),
                n=3,
                cutoff=0.5,
            )

            if suggestions:
                # Map back to original casing
                original_suggestions = [available_lower[s] for s in suggestions]
                errors.append(
                    f"Unknown table '{table_name}'. "
                    f"Did you mean: {', '.join(original_suggestions)}?"
                )
            else:
                errors.append(
                    f"Unknown table '{table_name}'. "
                    f"Available tables: {', '.join(sorted(available_tables)[:5])}..."
                )

    return errors


def _validate_columns(
    ast: exp.Expression,
    schema: dict[str, TableSchema],
) -> list[str]:
    """Validate column references exist in referenced tables.

    Args:
        ast: Parsed SQL AST.
        schema: Dict of table_name -> TableSchema.

    Returns:
        List of error messages for unknown columns.
    """
    errors = []

    # Get all referenced tables
    referenced_tables: set[str] = set()
    for table in ast.find_all(exp.Table):
        table_lower = table.name.lower()
        for schema_table in schema:
            if schema_table.lower() == table_lower:
                referenced_tables.add(schema_table)
                break

    if not referenced_tables:
        return []  # No tables to validate against

    # Build set of all valid columns from referenced tables
    valid_columns: set[str] = set()
    valid_columns_lower: dict[str, str] = {}
    for table_name in referenced_tables:
        table_schema = schema.get(table_name)
        if table_schema:
            for col_name in table_schema.get_column_names():
                valid_columns.add(col_name)
                valid_columns_lower[col_name.lower()] = col_name

    # Extract aliases from SELECT expressions to skip validation
    select_aliases: set[str] = set()
    for select in ast.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Alias):
                alias_name = projection.alias
                if alias_name:
                    select_aliases.add(alias_name.lower())

    # Check column references
    for column in ast.find_all(exp.Column):
        col_name = column.name
        col_lower = col_name.lower()

        # Skip star selects
        if col_name == "*":
            continue

        # Skip if column is actually a SELECT alias (e.g., used in ORDER BY)
        if col_lower in select_aliases:
            continue

        if col_lower not in valid_columns_lower:
            # Find similar column names
            suggestions = get_close_matches(
                col_lower,
                list(valid_columns_lower.keys()),
                n=3,
                cutoff=0.4,
            )

            if suggestions:
                original_suggestions = [valid_columns_lower[s] for s in suggestions]
                # Check if any have special characters requiring quotes
                quoted_suggestions = []
                for s in original_suggestions:
                    if "-" in s or " " in s:
                        quoted_suggestions.append(f'"{s}"')
                    else:
                        quoted_suggestions.append(s)

                errors.append(
                    f"Unknown column '{col_name}'. "
                    f"Did you mean: {', '.join(quoted_suggestions)}? "
                    "Use double quotes for columns with special characters."
                )
            else:
                sample_cols = sorted(valid_columns)[:5]
                errors.append(
                    f"Unknown column '{col_name}' in referenced tables. "
                    f"Available columns include: {', '.join(sample_cols)}..."
                )

    return errors


def _enforce_limit(
    ast: exp.Expression,
    original_sql: str,
) -> tuple[str, list[str]]:
    """Ensure SELECT has LIMIT clause, adding one if missing.

    Args:
        ast: Parsed SQL AST.
        original_sql: Original SQL string.

    Returns:
        Tuple of (corrected_sql, list of warnings).
    """
    warnings = []

    # Check for existing LIMIT
    limit_node = ast.find(exp.Limit)

    if limit_node:
        # Validate existing limit isn't too high
        limit_expr = limit_node.expression
        if isinstance(limit_expr, exp.Literal) and limit_expr.is_int:
            limit_value = int(limit_expr.this)
            if limit_value > MAX_LIMIT:
                # Reduce to max
                limit_node.set("expression", exp.Literal.number(MAX_LIMIT))
                warnings.append(f"LIMIT reduced from {limit_value} to {MAX_LIMIT}")
                return ast.sql(dialect="duckdb"), warnings

        return original_sql, warnings

    # Add LIMIT clause
    try:
        modified = ast.limit(DEFAULT_LIMIT)
        warnings.append(f"LIMIT {DEFAULT_LIMIT} automatically added")
        return modified.sql(dialect="duckdb"), warnings
    except Exception as e:
        # If modification fails, append manually
        logger.warning("limit_injection_failed", error=str(e))
        corrected = f"{original_sql.rstrip().rstrip(';')} LIMIT {DEFAULT_LIMIT}"
        warnings.append(f"LIMIT {DEFAULT_LIMIT} automatically added")
        return corrected, warnings


def _parse_schema_context(schema_context: str) -> dict[str, TableSchema]:
    """Parse schema context string into TableSchema dict (simplified).

    This is a simplified parser for schema context strings.
    In production, this would use the actual SchemaRegistry.

    Args:
        schema_context: Schema context string from state.

    Returns:
        Dict of table_name -> TableSchema (simplified).
    """
    from retail_insights.models.schema import ColumnSchema, TableSchema

    # Simple parsing for schema context like:
    # "Table: amazon_sales\nColumns: Amount, Category, Date..."
    if not schema_context:
        return {}

    result: dict[str, TableSchema] = {}
    current_table = None
    columns: list[ColumnSchema] = []

    for line in schema_context.split("\n"):
        line = line.strip()
        if line.startswith("Table:"):
            # Save previous table if exists
            if current_table and columns:
                result[current_table] = TableSchema(
                    name=current_table,
                    source_type="local",
                    source_path="",
                    columns=columns,
                )
            # Start new table
            current_table = line.replace("Table:", "").strip()
            columns = []
        elif line.startswith("Columns:"):
            # Parse column definitions
            cols_str = line.replace("Columns:", "").strip()
            # Handle format: "Name (TYPE), Name2 (TYPE2), ..."
            for col_part in cols_str.split(","):
                col_part = col_part.strip()
                if "(" in col_part:
                    # Extract name and type
                    name = col_part.split("(")[0].strip()
                    data_type = col_part.split("(")[1].replace(")", "").strip()
                else:
                    name = col_part
                    data_type = "VARCHAR"

                if name:
                    columns.append(ColumnSchema(name=name, data_type=data_type))
        elif ":" in line and current_table:
            # Handle "- column: type" format
            parts = line.split(":")
            if len(parts) >= 2:
                name = parts[0].strip().lstrip("-").strip()
                data_type = parts[1].strip()
                if name:
                    columns.append(ColumnSchema(name=name, data_type=data_type))

    # Save last table
    if current_table and columns:
        result[current_table] = TableSchema(
            name=current_table,
            source_type="local",
            source_path="",
            columns=columns,
        )

    return result


def create_mock_validator(
    is_valid: bool = True,
    errors: list[str] | None = None,
    corrected_sql: str | None = None,
    *,
    should_exceed_retry: bool = False,
):
    """Create a mock validator function for testing.

    Args:
        is_valid: Whether validation should pass.
        errors: List of error messages to return.
        corrected_sql: Corrected SQL to return.
        should_exceed_retry: If True, simulate retry limit exceeded.

    Returns:
        Async function matching validate_sql signature.
    """

    async def mock_validate_sql(state: RetailInsightsState) -> dict:
        if should_exceed_retry:
            return {
                "sql_is_valid": False,
                "validation_errors": [f"Maximum retry count ({MAX_RETRY_COUNT}) exceeded"],
                "validation_status": "failed",
            }

        result = {
            "sql_is_valid": is_valid,
            "validation_errors": errors,
            "validation_status": "valid" if is_valid else "invalid",
        }

        if corrected_sql:
            result["generated_sql"] = corrected_sql
            result["validation_status"] = "corrected"

        return result

    return mock_validate_sql
