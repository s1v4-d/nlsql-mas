"""Unit tests for SQL Validator agent node."""

import pytest

# Import sqlglot for AST tests
import sqlglot

from retail_insights.agents.nodes.validator import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_RETRY_COUNT,
    _check_security,
    _check_select_only,
    _enforce_limit,
    _parse_schema_context,
    _validate_columns,
    _validate_tables,
    create_mock_validator,
    validate_sql,
)
from retail_insights.agents.state import create_initial_state


class TestSQLSyntaxValidation:
    """Tests for SQL syntax validation."""

    @pytest.mark.asyncio
    async def test_valid_select_query(self) -> None:
        """Test validation of valid SELECT query."""
        state = create_initial_state("Show sales", "test-thread")
        state["generated_sql"] = "SELECT * FROM amazon_sales LIMIT 10"
        state["schema_context"] = "Table: amazon_sales\nColumns: Amount (FLOAT), Category (VARCHAR)"

        result = await validate_sql(state)

        assert result["sql_is_valid"] is True
        assert result["validation_status"] == "valid"
        assert result.get("validation_errors") == []

    @pytest.mark.asyncio
    async def test_invalid_syntax(self) -> None:
        """Test validation catches syntax errors."""
        state = create_initial_state("Show sales", "test-thread")
        state["generated_sql"] = "SELECT * FROM (SELECT a FROM t"  # Missing closing paren

        result = await validate_sql(state)

        assert result["sql_is_valid"] is False
        assert "syntax error" in result["validation_errors"][0].lower()

    @pytest.mark.asyncio
    async def test_empty_sql(self) -> None:
        """Test validation handles empty SQL."""
        state = create_initial_state("Show sales", "test-thread")
        state["generated_sql"] = None

        result = await validate_sql(state)

        assert result["sql_is_valid"] is False
        assert "No SQL query" in result["validation_errors"][0]


class TestSecurityValidation:
    """Tests for SQL security checks."""

    @pytest.mark.asyncio
    async def test_blocks_drop_statement(self) -> None:
        """Test that DROP statements are blocked."""
        state = create_initial_state("Drop table", "test-thread")
        state["generated_sql"] = "DROP TABLE amazon_sales"

        result = await validate_sql(state)

        assert result["sql_is_valid"] is False
        assert any("Blocked" in e or "DROP" in e for e in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_blocks_delete_statement(self) -> None:
        """Test that DELETE statements are blocked."""
        state = create_initial_state("Delete data", "test-thread")
        state["generated_sql"] = "DELETE FROM amazon_sales WHERE 1=1"

        result = await validate_sql(state)

        assert result["sql_is_valid"] is False
        assert any("DELETE" in e for e in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_blocks_insert_statement(self) -> None:
        """Test that INSERT statements are blocked."""
        state = create_initial_state("Insert data", "test-thread")
        state["generated_sql"] = "INSERT INTO amazon_sales VALUES (1, 2)"

        result = await validate_sql(state)

        assert result["sql_is_valid"] is False
        assert any("INSERT" in e for e in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_blocks_update_statement(self) -> None:
        """Test that UPDATE statements are blocked."""
        state = create_initial_state("Update data", "test-thread")
        state["generated_sql"] = "UPDATE amazon_sales SET Amount = 0"

        result = await validate_sql(state)

        assert result["sql_is_valid"] is False
        assert any("UPDATE" in e for e in result["validation_errors"])

    def test_check_security_function(self) -> None:
        """Test security check helper function."""
        # Valid SELECT
        ast = sqlglot.parse_one("SELECT * FROM t", dialect="duckdb")
        errors = _check_security(ast, "SELECT * FROM t")
        assert len(errors) == 0

        # DROP statement
        ast = sqlglot.parse_one("DROP TABLE t", dialect="duckdb")
        errors = _check_security(ast, "DROP TABLE t")
        assert len(errors) > 0
        assert "DROP" in errors[0] or "Blocked" in errors[0]


class TestSelectOnlyValidation:
    """Tests for SELECT-only enforcement."""

    def test_allows_select(self) -> None:
        """Test that SELECT is allowed."""
        ast = sqlglot.parse_one("SELECT * FROM t", dialect="duckdb")
        errors = _check_select_only(ast)
        assert len(errors) == 0

    def test_allows_union(self) -> None:
        """Test that UNION is allowed."""
        ast = sqlglot.parse_one("SELECT a FROM t UNION SELECT b FROM t2", dialect="duckdb")
        errors = _check_select_only(ast)
        assert len(errors) == 0

    def test_allows_cte(self) -> None:
        """Test that CTEs are allowed."""
        ast = sqlglot.parse_one(
            "WITH cte AS (SELECT a FROM t) SELECT * FROM cte",
            dialect="duckdb",
        )
        errors = _check_select_only(ast)
        assert len(errors) == 0


class TestTableValidation:
    """Tests for table existence validation."""

    def test_valid_table(self) -> None:
        """Test validation passes for existing table."""
        from retail_insights.models.schema import ColumnSchema, TableSchema

        ast = sqlglot.parse_one("SELECT * FROM amazon_sales", dialect="duckdb")
        schema = {
            "amazon_sales": TableSchema(
                name="amazon_sales",
                source_type="local",
                source_path="",
                columns=[ColumnSchema(name="Amount", data_type="FLOAT")],
            )
        }

        errors = _validate_tables(ast, schema)
        assert len(errors) == 0

    def test_unknown_table_with_suggestion(self) -> None:
        """Test that unknown tables get suggestions."""
        from retail_insights.models.schema import ColumnSchema, TableSchema

        ast = sqlglot.parse_one("SELECT * FROM amazon_sale", dialect="duckdb")  # Typo
        schema = {
            "amazon_sales": TableSchema(
                name="amazon_sales",
                source_type="local",
                source_path="",
                columns=[ColumnSchema(name="Amount", data_type="FLOAT")],
            )
        }

        errors = _validate_tables(ast, schema)
        assert len(errors) == 1
        assert "Did you mean" in errors[0]
        assert "amazon_sales" in errors[0]

    def test_unknown_table_no_match(self) -> None:
        """Test unknown table with no similar matches."""
        from retail_insights.models.schema import ColumnSchema, TableSchema

        ast = sqlglot.parse_one("SELECT * FROM xyz_table", dialect="duckdb")
        schema = {
            "amazon_sales": TableSchema(
                name="amazon_sales",
                source_type="local",
                source_path="",
                columns=[ColumnSchema(name="Amount", data_type="FLOAT")],
            )
        }

        errors = _validate_tables(ast, schema)
        assert len(errors) == 1
        assert "Available tables" in errors[0]


class TestColumnValidation:
    """Tests for column existence validation."""

    def test_valid_column(self) -> None:
        """Test validation passes for existing column."""
        from retail_insights.models.schema import ColumnSchema, TableSchema

        ast = sqlglot.parse_one("SELECT Amount FROM amazon_sales", dialect="duckdb")
        schema = {
            "amazon_sales": TableSchema(
                name="amazon_sales",
                source_type="local",
                source_path="",
                columns=[
                    ColumnSchema(name="Amount", data_type="FLOAT"),
                    ColumnSchema(name="Category", data_type="VARCHAR"),
                ],
            )
        }

        errors = _validate_columns(ast, schema)
        assert len(errors) == 0

    def test_unknown_column_with_suggestion(self) -> None:
        """Test that unknown columns get suggestions."""
        from retail_insights.models.schema import ColumnSchema, TableSchema

        ast = sqlglot.parse_one("SELECT Amoun FROM amazon_sales", dialect="duckdb")  # Typo
        schema = {
            "amazon_sales": TableSchema(
                name="amazon_sales",
                source_type="local",
                source_path="",
                columns=[
                    ColumnSchema(name="Amount", data_type="FLOAT"),
                    ColumnSchema(name="Category", data_type="VARCHAR"),
                ],
            )
        }

        errors = _validate_columns(ast, schema)
        assert len(errors) == 1
        assert "Did you mean" in errors[0]
        assert "Amount" in errors[0]

    def test_column_with_special_chars_suggestion(self) -> None:
        """Test suggestions for columns with special characters."""
        from retail_insights.models.schema import ColumnSchema, TableSchema

        ast = sqlglot.parse_one('SELECT "ship-stat" FROM amazon_sales', dialect="duckdb")  # Typo
        schema = {
            "amazon_sales": TableSchema(
                name="amazon_sales",
                source_type="local",
                source_path="",
                columns=[
                    ColumnSchema(name="ship-state", data_type="VARCHAR"),
                    ColumnSchema(name="ship-city", data_type="VARCHAR"),
                ],
            )
        }

        errors = _validate_columns(ast, schema)
        assert len(errors) == 1
        # Should suggest quoted version
        assert '"ship-state"' in errors[0] or "ship-state" in errors[0]

    def test_star_select_allowed(self) -> None:
        """Test that SELECT * doesn't trigger column validation errors."""
        from retail_insights.models.schema import ColumnSchema, TableSchema

        ast = sqlglot.parse_one("SELECT * FROM amazon_sales", dialect="duckdb")
        schema = {
            "amazon_sales": TableSchema(
                name="amazon_sales",
                source_type="local",
                source_path="",
                columns=[ColumnSchema(name="Amount", data_type="FLOAT")],
            )
        }

        errors = _validate_columns(ast, schema)
        assert len(errors) == 0


class TestLimitEnforcement:
    """Tests for LIMIT clause enforcement."""

    def test_adds_limit_when_missing(self) -> None:
        """Test that LIMIT is added when missing."""
        ast = sqlglot.parse_one("SELECT * FROM t", dialect="duckdb")
        corrected, warnings = _enforce_limit(ast, "SELECT * FROM t")

        assert "LIMIT" in corrected.upper()
        assert str(DEFAULT_LIMIT) in corrected
        assert len(warnings) == 1
        assert "automatically added" in warnings[0]

    def test_preserves_existing_limit(self) -> None:
        """Test that existing valid LIMIT is preserved."""
        original = "SELECT * FROM t LIMIT 50"
        ast = sqlglot.parse_one(original, dialect="duckdb")
        corrected, warnings = _enforce_limit(ast, original)

        assert corrected == original
        assert len(warnings) == 0

    def test_reduces_excessive_limit(self) -> None:
        """Test that excessive LIMIT is reduced."""
        original = "SELECT * FROM t LIMIT 10000"
        ast = sqlglot.parse_one(original, dialect="duckdb")
        corrected, warnings = _enforce_limit(ast, original)

        assert str(MAX_LIMIT) in corrected
        assert "10000" not in corrected
        assert len(warnings) == 1
        assert "reduced" in warnings[0].lower()

    @pytest.mark.asyncio
    async def test_auto_limit_in_full_validation(self) -> None:
        """Test LIMIT is auto-added during full validation."""
        state = create_initial_state("Show sales", "test-thread")
        state["generated_sql"] = "SELECT * FROM amazon_sales"
        state["schema_context"] = "Table: amazon_sales\nColumns: Amount (FLOAT)"

        result = await validate_sql(state)

        # SQL should be valid (with corrected LIMIT)
        assert result["sql_is_valid"] is True
        assert result["validation_status"] == "corrected"
        assert "LIMIT" in result["generated_sql"].upper()


class TestRetryTracking:
    """Tests for retry count management."""

    @pytest.mark.asyncio
    async def test_exceeds_max_retry(self) -> None:
        """Test that validation fails when max retry exceeded."""
        state = create_initial_state("Show sales", "test-thread")
        state["generated_sql"] = "SELECT * FROM amazon_sales LIMIT 10"
        state["retry_count"] = MAX_RETRY_COUNT + 1

        result = await validate_sql(state)

        assert result["sql_is_valid"] is False
        assert "Maximum retry" in result["validation_errors"][0]
        assert result["validation_status"] == "failed"

    @pytest.mark.asyncio
    async def test_within_retry_limit(self) -> None:
        """Test validation proceeds when within retry limit."""
        state = create_initial_state("Show sales", "test-thread")
        state["generated_sql"] = "SELECT * FROM amazon_sales LIMIT 10"
        state["schema_context"] = "Table: amazon_sales\nColumns: Amount (FLOAT)"
        state["retry_count"] = MAX_RETRY_COUNT

        result = await validate_sql(state)

        # Should not fail due to retry count
        assert "Maximum retry" not in str(result.get("validation_errors", []))


class TestSchemaContextParsing:
    """Tests for schema context string parsing."""

    def test_parse_basic_schema(self) -> None:
        """Test parsing basic schema context."""
        context = """Table: amazon_sales
Columns: Amount (FLOAT), Category (VARCHAR), Date (VARCHAR)"""

        schema = _parse_schema_context(context)

        assert "amazon_sales" in schema
        assert len(schema["amazon_sales"].columns) == 3
        assert schema["amazon_sales"].get_column("Amount") is not None
        assert schema["amazon_sales"].get_column("Category") is not None

    def test_parse_empty_context(self) -> None:
        """Test parsing empty context returns empty dict."""
        schema = _parse_schema_context("")
        assert schema == {}

    def test_parse_multiline_schema(self) -> None:
        """Test parsing multi-line schema context."""
        context = """Table: amazon_sales
Columns: Amount (FLOAT), Category (VARCHAR)
Table: products
Columns: ProductID (INTEGER), Name (VARCHAR)"""

        schema = _parse_schema_context(context)

        assert len(schema) == 2
        assert "amazon_sales" in schema
        assert "products" in schema


class TestMockValidator:
    """Tests for mock validator helper."""

    @pytest.mark.asyncio
    async def test_mock_valid(self) -> None:
        """Test mock validator returns valid result."""
        mock = create_mock_validator(is_valid=True)
        state = create_initial_state("Test", "test-thread")

        result = await mock(state)

        assert result["sql_is_valid"] is True
        assert result["validation_status"] == "valid"

    @pytest.mark.asyncio
    async def test_mock_invalid_with_errors(self) -> None:
        """Test mock validator returns errors."""
        mock = create_mock_validator(
            is_valid=False,
            errors=["Unknown table 'xyz'", "Missing LIMIT"],
        )
        state = create_initial_state("Test", "test-thread")

        result = await mock(state)

        assert result["sql_is_valid"] is False
        assert len(result["validation_errors"]) == 2

    @pytest.mark.asyncio
    async def test_mock_with_correction(self) -> None:
        """Test mock validator with corrected SQL."""
        mock = create_mock_validator(
            is_valid=True,
            corrected_sql="SELECT * FROM t LIMIT 100",
        )
        state = create_initial_state("Test", "test-thread")

        result = await mock(state)

        assert result["sql_is_valid"] is True
        assert result["generated_sql"] == "SELECT * FROM t LIMIT 100"
        assert result["validation_status"] == "corrected"

    @pytest.mark.asyncio
    async def test_mock_retry_exceeded(self) -> None:
        """Test mock validator simulating retry exceeded."""
        mock = create_mock_validator(should_exceed_retry=True)
        state = create_initial_state("Test", "test-thread")

        result = await mock(state)

        assert result["sql_is_valid"] is False
        assert "Maximum retry" in result["validation_errors"][0]


class TestIntegration:
    """Integration tests for validator agent."""

    @pytest.mark.asyncio
    async def test_full_validation_pipeline(self) -> None:
        """Test full validation with all checks."""
        state = create_initial_state("Get sales by category", "test-thread")
        state["generated_sql"] = """
            SELECT Category, SUM(Amount) as total
            FROM amazon_sales
            GROUP BY Category
            ORDER BY total DESC
        """
        state["schema_context"] = """Table: amazon_sales
Columns: Amount (FLOAT), Category (VARCHAR), Date (VARCHAR), Status (VARCHAR)"""

        result = await validate_sql(state)

        # Should be valid with auto-added LIMIT
        assert result["sql_is_valid"] is True
        assert "LIMIT" in result["generated_sql"].upper()

    @pytest.mark.asyncio
    async def test_validation_with_quoted_columns(self) -> None:
        """Test validation with DuckDB quoted identifiers."""
        state = create_initial_state("Get by state", "test-thread")
        state["generated_sql"] = (
            'SELECT "ship-state", COUNT(*) FROM amazon_sales GROUP BY "ship-state" LIMIT 10'
        )
        state["schema_context"] = """Table: amazon_sales
Columns: Amount (FLOAT), ship-state (VARCHAR), ship-city (VARCHAR)"""

        result = await validate_sql(state)

        assert result["sql_is_valid"] is True

    @pytest.mark.asyncio
    async def test_validation_case_insensitive_matching(self) -> None:
        """Test that table and column matching is case-insensitive."""
        state = create_initial_state("Get sales", "test-thread")
        state["generated_sql"] = "SELECT AMOUNT FROM AMAZON_SALES LIMIT 10"
        state["schema_context"] = """Table: amazon_sales
Columns: Amount (FLOAT), Category (VARCHAR)"""

        result = await validate_sql(state)

        # Should pass despite case differences
        assert result["sql_is_valid"] is True
