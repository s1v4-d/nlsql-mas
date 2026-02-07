"""Integration tests for DuckDB data engine.

These tests use an in-memory DuckDB instance with sample data
to verify connector and query runner functionality.
"""

from pathlib import Path

import pytest

from retail_insights.engine.connector import DuckDBConnector
from retail_insights.engine.query_runner import QueryRunner


@pytest.fixture
def temp_parquet_file(tmp_path: Path):
    """Create a temporary Parquet file with sample data."""
    # We use DuckDB to create the parquet file
    import duckdb

    file_path = tmp_path / "sample_sales.parquet"

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE sample_data AS
        SELECT *
        FROM (VALUES
            (1, 'Widget A', 'Electronics', 99.99, 10, DATE '2024-01-01'),
            (2, 'Widget B', 'Electronics', 149.99, 5, DATE '2024-01-02'),
            (3, 'Gadget X', 'Accessories', 29.99, 20, DATE '2024-01-03'),
            (4, 'Gadget Y', 'Accessories', 39.99, 15, DATE '2024-01-04'),
            (5, 'Device Z', 'Electronics', 299.99, 3, DATE '2024-01-05')
        ) AS t(id, product_name, category, price, quantity, sale_date)
    """)
    conn.execute(f"COPY sample_data TO '{file_path}' (FORMAT PARQUET)")
    conn.close()

    return file_path


@pytest.fixture
def connector():
    """Create a fresh DuckDB connector for testing."""
    # Reset singleton to ensure clean state
    DuckDBConnector.reset_instance()

    conn = DuckDBConnector(
        data_path="./data",
        memory_limit="256MB",
        threads=2,
        read_only=False,  # Need write for test setup
    )
    yield conn
    conn.close()
    DuckDBConnector.reset_instance()


@pytest.fixture
def query_runner(connector: DuckDBConnector):
    """Create a QueryRunner with the test connector."""
    return QueryRunner(
        connector=connector,
        max_rows=100,
        enforce_limit=True,
    )


class TestDuckDBConnector:
    """Tests for DuckDBConnector."""

    def test_connection_creation(self, connector: DuckDBConnector):
        """Test that connection is created successfully."""
        conn = connector.get_connection()
        assert conn is not None

        # Verify we can execute a simple query
        result = conn.execute("SELECT 1 as value").fetchall()
        assert result == [(1,)]

    def test_memory_limit_applied(self, connector: DuckDBConnector):
        """Test that memory limit is configured."""
        conn = connector.get_connection()
        result = conn.execute("SELECT current_setting('memory_limit')").fetchone()
        # Memory limit should be set (contains some value like "244.1 MiB" or "256.0 MiB")
        assert "MiB" in str(result[0]) or "GiB" in str(result[0]) or "MB" in str(result[0])

    def test_thread_limit_applied(self, connector: DuckDBConnector):
        """Test that thread limit is configured."""
        conn = connector.get_connection()
        result = conn.execute("SELECT current_setting('threads')").fetchone()
        assert int(result[0]) == 2

    def test_register_parquet(self, connector: DuckDBConnector, temp_parquet_file: Path):
        """Test registering a Parquet file as a table."""
        connector.register_parquet("test_sales", temp_parquet_file)

        # Verify table is accessible
        result = connector.execute_fetchall("SELECT COUNT(*) FROM test_sales")
        assert result[0][0] == 5

    def test_list_tables(self, connector: DuckDBConnector, temp_parquet_file: Path):
        """Test listing registered tables."""
        connector.register_parquet("sales_table", temp_parquet_file)

        tables = connector.list_tables()
        assert "sales_table" in tables

    def test_get_table_schema(self, connector: DuckDBConnector, temp_parquet_file: Path):
        """Test getting table schema information."""
        connector.register_parquet("schema_test", temp_parquet_file)

        schema = connector.get_table_schema("schema_test")

        column_names = [col["name"] for col in schema]
        assert "id" in column_names
        assert "product_name" in column_names
        assert "price" in column_names

    def test_execute_fetchdf(self, connector: DuckDBConnector, temp_parquet_file: Path):
        """Test fetching results as DataFrame."""
        connector.register_parquet("df_test", temp_parquet_file)

        df = connector.execute_fetchdf("SELECT * FROM df_test ORDER BY id LIMIT 3")

        assert len(df) == 3
        assert list(df.columns) == [
            "id",
            "product_name",
            "category",
            "price",
            "quantity",
            "sale_date",
        ]

    def test_context_manager(self, connector: DuckDBConnector):
        """Test connector as context manager."""
        with connector.connection() as conn:
            result = conn.execute("SELECT 42 as answer").fetchone()
            assert result[0] == 42


class TestQueryRunner:
    """Tests for QueryRunner."""

    def test_valid_select_query(
        self,
        query_runner: QueryRunner,
        connector: DuckDBConnector,
        temp_parquet_file: Path,
    ):
        """Test executing a valid SELECT query."""
        connector.register_parquet("products", temp_parquet_file)

        result = query_runner.execute("SELECT * FROM products")

        assert result.success is True
        assert result.row_count == 5
        assert len(result.columns) == 6
        assert "product_name" in result.columns

    def test_limit_enforcement(
        self,
        tmp_path: Path,
    ):
        """Test that LIMIT is automatically added."""
        import duckdb

        # Create test parquet file
        file_path = tmp_path / "limit_test.parquet"
        temp_conn = duckdb.connect(":memory:")
        temp_conn.execute("""
            CREATE TABLE data AS SELECT * FROM (VALUES
                (1, 'A'), (2, 'B'), (3, 'C'), (4, 'D'), (5, 'E')
            ) AS t(id, name)
        """)
        temp_conn.execute(f"COPY data TO '{file_path}' (FORMAT PARQUET)")
        temp_conn.close()

        # Create a completely fresh connector for this test
        DuckDBConnector.reset_instance()
        fresh_connector = DuckDBConnector(
            data_path="./data",
            memory_limit="256MB",
            threads=2,
            read_only=False,
        )

        try:
            fresh_connector.register_parquet("limit_test_table", file_path)

            runner = QueryRunner(connector=fresh_connector, max_rows=3, enforce_limit=True)

            # Debug: verify attributes
            assert runner.enforce_limit is True, f"enforce_limit is {runner.enforce_limit}"
            assert runner.max_rows == 3, f"max_rows is {runner.max_rows}"

            # First verify the SQL transformation works
            test_sql = "SELECT * FROM limit_test_table"
            final_sql = runner._ensure_limit(test_sql)
            assert "LIMIT 3" in final_sql, f"final_sql is: {final_sql}"

            # Then verify execution respects the limit
            result = runner.execute(test_sql)
            assert result.row_count <= 3
        finally:
            fresh_connector.close()
            DuckDBConnector.reset_instance()

    def test_existing_limit_preserved(
        self,
        query_runner: QueryRunner,
        connector: DuckDBConnector,
        temp_parquet_file: Path,
    ):
        """Test that existing LIMIT clause is preserved."""
        connector.register_parquet("preserve_limit", temp_parquet_file)

        result = query_runner.execute("SELECT * FROM preserve_limit LIMIT 2")

        assert result.row_count == 2

    def test_validate_sql_blocks_write(self, query_runner: QueryRunner):
        """Test that write operations are blocked."""
        is_valid, errors = query_runner.validate_sql("DELETE FROM users")
        assert is_valid is False
        assert any("Write operation" in e for e in errors)

    def test_validate_sql_blocks_drop(self, query_runner: QueryRunner):
        """Test that DROP is blocked."""
        is_valid, errors = query_runner.validate_sql("DROP TABLE users")
        assert is_valid is False

    def test_validate_sql_blocks_insert(self, query_runner: QueryRunner):
        """Test that INSERT is blocked."""
        is_valid, errors = query_runner.validate_sql("INSERT INTO users VALUES (1)")
        assert is_valid is False

    def test_validate_sql_blocks_multiple_statements(self, query_runner: QueryRunner):
        """Test that multiple statements are blocked."""
        is_valid, errors = query_runner.validate_sql("SELECT 1; DROP TABLE users")
        assert is_valid is False
        assert any("Multiple statements" in e for e in errors)

    def test_validate_sql_blocks_comments(self, query_runner: QueryRunner):
        """Test that SQL comments are blocked."""
        is_valid, errors = query_runner.validate_sql("SELECT 1 -- comment")
        assert is_valid is False

    def test_validate_sql_allows_select(self, query_runner: QueryRunner):
        """Test that valid SELECT is allowed."""
        is_valid, errors = query_runner.validate_sql("SELECT * FROM users LIMIT 10")
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_sql_allows_with(self, query_runner: QueryRunner):
        """Test that WITH (CTE) queries are allowed."""
        sql = """
        WITH recent_sales AS (
            SELECT * FROM orders WHERE date > '2024-01-01'
        )
        SELECT * FROM recent_sales
        """
        is_valid, errors = query_runner.validate_sql(sql)
        assert is_valid is True

    def test_aggregation_query(
        self,
        query_runner: QueryRunner,
        connector: DuckDBConnector,
        temp_parquet_file: Path,
    ):
        """Test executing an aggregation query."""
        connector.register_parquet("agg_data", temp_parquet_file)

        result = query_runner.execute("""
            SELECT category, COUNT(*) as count, SUM(price * quantity) as revenue
            FROM agg_data
            GROUP BY category
            ORDER BY revenue DESC
        """)

        assert result.success is True
        assert result.row_count == 2  # Two categories
        assert "category" in result.columns
        assert "revenue" in result.columns

    def test_execution_time_tracked(
        self,
        query_runner: QueryRunner,
        connector: DuckDBConnector,
        temp_parquet_file: Path,
    ):
        """Test that execution time is tracked."""
        connector.register_parquet("timing_test", temp_parquet_file)

        result = query_runner.execute("SELECT * FROM timing_test")

        assert result.execution_time_ms >= 0

    def test_table_info(
        self,
        query_runner: QueryRunner,
        connector: DuckDBConnector,
        temp_parquet_file: Path,
    ):
        """Test getting table information."""
        query_runner.register_table("info_table", str(temp_parquet_file), "local")

        info = query_runner.get_table_info("info_table")

        assert info["logical_name"] == "info_table"
        assert info["source_type"] == "local"
        assert len(info["columns"]) == 6

    def test_list_available_tables(
        self,
        query_runner: QueryRunner,
        connector: DuckDBConnector,
        temp_parquet_file: Path,
    ):
        """Test listing available tables."""
        query_runner.register_table("list_test", str(temp_parquet_file))

        tables = query_runner.list_available_tables()

        assert "list_test" in tables


class TestQueryRunnerErrors:
    """Tests for QueryRunner error handling."""

    def test_execute_invalid_sql_raises_validation_error(self, query_runner: QueryRunner):
        """Test that invalid SQL raises ValidationError."""
        from retail_insights.core.exceptions import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            query_runner.execute("DELETE FROM users")

        assert "Write operation" in str(exc_info.value)

    def test_execute_nonexistent_table_raises_execution_error(self, query_runner: QueryRunner):
        """Test that querying nonexistent table raises ExecutionError."""
        from retail_insights.core.exceptions import ExecutionError

        with pytest.raises(ExecutionError):
            query_runner.execute("SELECT * FROM nonexistent_table_xyz")

    def test_get_table_info_nonexistent_raises_value_error(self, query_runner: QueryRunner):
        """Test that getting info for nonexistent table raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            query_runner.get_table_info("does_not_exist")

        assert "Table not found" in str(exc_info.value)


class TestConnectorSingleton:
    """Tests for connector singleton behavior."""

    def test_singleton_returns_same_instance(self):
        """Test that get_instance returns same object."""
        DuckDBConnector.reset_instance()

        instance1 = DuckDBConnector.get_instance()
        instance2 = DuckDBConnector.get_instance()

        assert instance1 is instance2

        DuckDBConnector.reset_instance()

    def test_reset_clears_singleton(self):
        """Test that reset_instance clears the singleton."""
        DuckDBConnector.reset_instance()

        instance1 = DuckDBConnector.get_instance()
        DuckDBConnector.reset_instance()
        instance2 = DuckDBConnector.get_instance()

        assert instance1 is not instance2

        DuckDBConnector.reset_instance()
