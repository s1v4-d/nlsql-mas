"""Unit tests for schema registry and related models."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from retail_insights.models.schema import (
    ColumnSchema,
    DataSource,
    SchemaRegistryState,
    TableSchema,
)


class TestColumnSchema:
    """Tests for ColumnSchema model."""

    def test_valid_column_schema(self) -> None:
        """Test creating a valid ColumnSchema."""
        col = ColumnSchema(
            name="Category",
            data_type="VARCHAR",
            nullable=False,
            description="Product category",
            sample_values=["Set", "Kurta", "Dress"],
        )
        assert col.name == "Category"
        assert col.data_type == "VARCHAR"
        assert col.nullable is False
        assert col.description == "Product category"
        assert col.sample_values == ["Set", "Kurta", "Dress"]

    def test_default_values(self) -> None:
        """Test ColumnSchema default values."""
        col = ColumnSchema(name="Amount", data_type="DOUBLE")
        assert col.nullable is True
        assert col.description is None
        assert col.sample_values == []

    def test_name_required(self) -> None:
        """Test that name is required."""
        with pytest.raises(PydanticValidationError):
            ColumnSchema(data_type="VARCHAR")  # type: ignore


class TestTableSchema:
    """Tests for TableSchema model."""

    def test_valid_table_schema(self) -> None:
        """Test creating a valid TableSchema."""
        table = TableSchema(
            name="amazon_sales",
            source_type="local",
            source_path="data/amazon_sales.parquet",
            columns=[
                ColumnSchema(name="Category", data_type="VARCHAR"),
                ColumnSchema(name="Amount", data_type="DOUBLE"),
            ],
            row_count=128976,
            file_format="parquet",
        )
        assert table.name == "amazon_sales"
        assert table.source_type == "local"
        assert table.source_path == "data/amazon_sales.parquet"
        assert len(table.columns) == 2
        assert table.row_count == 128976
        assert table.file_format == "parquet"

    def test_source_type_validation(self) -> None:
        """Test source_type must be s3, local, or postgres."""
        with pytest.raises(PydanticValidationError) as exc_info:
            TableSchema(
                name="test",
                source_type="invalid",
                source_path="path",
            )
        assert "pattern" in str(exc_info.value).lower() or "match" in str(exc_info.value).lower()

    def test_valid_source_types(self) -> None:
        """Test all valid source types are accepted."""
        for source_type in ["s3", "local", "postgres"]:
            table = TableSchema(
                name="test",
                source_type=source_type,
                source_path="path",
            )
            assert table.source_type == source_type

    def test_get_column_names(self) -> None:
        """Test get_column_names helper method."""
        table = TableSchema(
            name="test",
            source_type="local",
            source_path="path",
            columns=[
                ColumnSchema(name="col1", data_type="VARCHAR"),
                ColumnSchema(name="col2", data_type="INTEGER"),
                ColumnSchema(name="col3", data_type="DOUBLE"),
            ],
        )
        assert table.get_column_names() == ["col1", "col2", "col3"]

    def test_get_column_names_empty(self) -> None:
        """Test get_column_names with no columns."""
        table = TableSchema(
            name="test",
            source_type="local",
            source_path="path",
        )
        assert table.get_column_names() == []


class TestDataSource:
    """Tests for DataSource model."""

    def test_valid_s3_source(self) -> None:
        """Test creating a valid S3 data source."""
        source = DataSource(
            type="s3",
            path="s3://mybucket/data",
            file_pattern="**/*.parquet",
        )
        assert source.type == "s3"
        assert source.path == "s3://mybucket/data"
        assert source.file_pattern == "**/*.parquet"
        assert source.enabled is True

    def test_valid_local_source(self) -> None:
        """Test creating a valid local data source."""
        source = DataSource(
            type="local",
            path="/data/sales",
            file_pattern="*.csv",
            enabled=False,
        )
        assert source.type == "local"
        assert source.path == "/data/sales"
        assert source.file_pattern == "*.csv"
        assert source.enabled is False

    def test_valid_postgres_source(self) -> None:
        """Test creating a valid PostgreSQL data source."""
        source = DataSource(
            type="postgres",
            path="postgresql://user:pass@host:5432/db",
        )
        assert source.type == "postgres"

    def test_type_validation(self) -> None:
        """Test type must be s3, local, or postgres."""
        with pytest.raises(PydanticValidationError):
            DataSource(type="mysql", path="path")  # type: ignore

    def test_default_file_pattern(self) -> None:
        """Test default file pattern is set."""
        source = DataSource(type="local", path="/data")
        assert source.file_pattern == "*.parquet"


class TestSchemaRegistryState:
    """Tests for SchemaRegistryState model."""

    def test_default_state(self) -> None:
        """Test default schema registry state."""
        state = SchemaRegistryState()
        assert state.tables == {}
        assert state.last_refresh is None
        assert state.source_stats == {}
        assert state.is_stale is True

    def test_state_with_tables(self) -> None:
        """Test state with tables populated."""
        tables = {
            "sales": TableSchema(
                name="sales",
                source_type="local",
                source_path="data/sales.parquet",
            ),
        }
        state = SchemaRegistryState(
            tables=tables,
            last_refresh=datetime.now(),
            source_stats={"local": 1},
            is_stale=False,
        )
        assert len(state.tables) == 1
        assert "sales" in state.tables
        assert state.source_stats["local"] == 1
        assert state.is_stale is False


class TestSchemaRegistry:
    """Tests for SchemaRegistry class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> None:
        """Reset singleton before each test."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        SchemaRegistry.reset_instance()

    def test_singleton_instance(self) -> None:
        """Test singleton pattern works correctly."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        instance1 = SchemaRegistry.get_instance()
        instance2 = SchemaRegistry.get_instance()
        assert instance1 is instance2

    def test_reset_instance(self) -> None:
        """Test singleton reset works."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        instance1 = SchemaRegistry.get_instance()
        SchemaRegistry.reset_instance()
        instance2 = SchemaRegistry.get_instance()
        assert instance1 is not instance2

    def test_add_source(self) -> None:
        """Test adding a data source."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry()
        source = DataSource(type="local", path="/data/test")
        registry.add_source(source)
        assert len(registry._sources) == 1
        assert registry._sources[0] == source

    def test_is_stale_initially(self) -> None:
        """Test registry is stale when first created."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry()
        assert registry.is_stale is True

    def test_is_stale_after_refresh(self) -> None:
        """Test registry is not stale after refresh."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry(sources=[])
        registry.refresh_schema()
        assert registry.is_stale is False

    def test_is_stale_after_ttl_expires(self) -> None:
        """Test registry becomes stale after TTL expires."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry(sources=[], cache_ttl=1)
        registry.refresh_schema()
        assert registry.is_stale is False

        # Simulate time passing
        registry._last_refresh = datetime.now() - timedelta(seconds=2)
        assert registry.is_stale is True

    def test_get_state_empty(self) -> None:
        """Test getting state from empty registry."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry()
        state = registry.get_state()
        assert len(state.tables) == 0
        assert state.last_refresh is None
        assert state.is_stale is True

    def test_get_valid_tables_empty(self) -> None:
        """Test getting valid tables from empty registry."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry(sources=[])
        # Force refresh to set _last_refresh
        registry.refresh_schema()
        tables = registry.get_valid_tables()
        assert tables == []

    def test_get_valid_columns_table_not_found(self) -> None:
        """Test getting columns for non-existent table."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry(sources=[])
        registry.refresh_schema()
        columns = registry.get_valid_columns("nonexistent")
        assert columns == []

    def test_get_schema_context_empty(self) -> None:
        """Test getting schema context from empty registry."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry(sources=[])
        registry.refresh_schema()
        context = registry.get_schema_context()
        assert "No tables discovered" in context

    @patch("retail_insights.engine.schema_registry.SchemaRegistry._discover_local_files")
    def test_discover_local_files_called(self, mock_discover: MagicMock) -> None:
        """Test local file discovery is called for local sources."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        mock_discover.return_value = {}
        source = DataSource(type="local", path="/data/test")
        registry = SchemaRegistry(sources=[source])
        registry.refresh_schema()
        mock_discover.assert_called_once_with(source)

    def test_refresh_updates_cache(self) -> None:
        """Test refresh updates the cache with discovered schemas."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        registry = SchemaRegistry(sources=[])

        # Manually populate cache to simulate discovery
        with registry._cache_lock:
            registry._cache["test_table"] = TableSchema(
                name="test_table",
                source_type="local",
                source_path="/test",
            )

        # After refresh (with no sources), cache should be cleared
        registry.refresh_schema()
        assert len(registry.get_schema()) == 0


class TestSchemaRegistryConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> None:
        """Reset singleton before each test."""
        from retail_insights.engine.schema_registry import SchemaRegistry

        SchemaRegistry.reset_instance()

    def test_get_schema_registry(self) -> None:
        """Test get_schema_registry returns singleton."""
        from retail_insights.engine.schema_registry import get_schema_registry

        registry1 = get_schema_registry()
        registry2 = get_schema_registry()
        assert registry1 is registry2

    def test_get_valid_tables_function(self) -> None:
        """Test get_valid_tables convenience function."""
        from retail_insights.engine.schema_registry import (
            SchemaRegistry,
            get_valid_tables,
        )

        # Get fresh instance and refresh
        registry = SchemaRegistry.get_instance()
        registry.refresh_schema()
        tables = get_valid_tables()
        assert isinstance(tables, list)

    def test_get_valid_columns_function(self) -> None:
        """Test get_valid_columns convenience function."""
        from retail_insights.engine.schema_registry import (
            SchemaRegistry,
            get_valid_columns,
        )

        registry = SchemaRegistry.get_instance()
        registry.refresh_schema()
        columns = get_valid_columns("nonexistent")
        assert columns == []

    def test_get_schema_context_function(self) -> None:
        """Test get_schema_context convenience function."""
        from retail_insights.engine.schema_registry import (
            SchemaRegistry,
            get_schema_context,
        )

        registry = SchemaRegistry.get_instance()
        registry.refresh_schema()
        context = get_schema_context()
        assert isinstance(context, str)
