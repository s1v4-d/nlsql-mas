"""Integration tests for admin API routes.

These tests verify the admin routes work correctly with
the schema registry.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from retail_insights.api.routes.admin import router
from retail_insights.engine.schema_registry import SchemaRegistry


@pytest.fixture(autouse=True)
def mock_env():
    """Set required environment variables for tests."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-api-key"}):
        # Clear cached settings
        from retail_insights.core.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset schema registry singleton before each test."""
    SchemaRegistry.reset_instance()
    yield
    SchemaRegistry.reset_instance()


@pytest.fixture
def app():
    """Create a test FastAPI app with admin routes."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app: FastAPI):
    """Create a test client with a valid API key."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Headers with valid admin API key."""
    return {"X-Admin-API-Key": "dev-admin-key"}


@pytest.fixture
def invalid_auth_headers():
    """Headers with invalid admin API key."""
    return {"X-Admin-API-Key": "invalid-key"}


class TestAdminAuthentication:
    """Tests for admin route authentication."""

    def test_missing_api_key(self, client: TestClient) -> None:
        """Test request without API key is rejected."""
        response = client.get("/admin/schema")
        assert response.status_code == 401
        assert "Missing X-Admin-API-Key" in response.json()["detail"]

    def test_invalid_api_key(self, client: TestClient, invalid_auth_headers: dict) -> None:
        """Test request with invalid API key is rejected."""
        response = client.get("/admin/schema", headers=invalid_auth_headers)
        assert response.status_code == 403
        assert "Invalid admin API key" in response.json()["detail"]

    def test_valid_api_key(self, client: TestClient, auth_headers: dict) -> None:
        """Test request with valid API key is accepted."""
        response = client.get("/admin/schema", headers=auth_headers)
        assert response.status_code == 200


class TestGetSchemaState:
    """Tests for GET /admin/schema endpoint."""

    def test_get_empty_schema_state(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting schema state from empty registry."""
        response = client.get("/admin/schema", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["tables"] == {}
        assert data["is_stale"] is True

    def test_get_schema_state_has_correct_fields(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Test schema state response has all required fields."""
        response = client.get("/admin/schema", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "tables" in data
        assert "last_refresh" in data
        assert "source_stats" in data
        assert "is_stale" in data


class TestRefreshSchema:
    """Tests for POST /admin/schema/refresh endpoint."""

    def test_refresh_schema_empty(self, client: TestClient, auth_headers: dict) -> None:
        """Test refreshing schema with no sources."""
        response = client.post("/admin/schema/refresh", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["tables_discovered"] == 0

    def test_refresh_updates_last_refresh(self, client: TestClient, auth_headers: dict) -> None:
        """Test refresh updates last_refresh timestamp."""
        # First check it's stale
        response = client.get("/admin/schema", headers=auth_headers)
        assert response.json()["is_stale"] is True

        # Refresh
        response = client.post("/admin/schema/refresh", headers=auth_headers)
        assert response.status_code == 200

        # Check it's no longer stale
        response = client.get("/admin/schema", headers=auth_headers)
        assert response.json()["is_stale"] is False


class TestAddSource:
    """Tests for POST /admin/schema/sources endpoint."""

    def test_add_local_source(self, client: TestClient, auth_headers: dict) -> None:
        """Test adding a local data source."""
        source_data = {
            "source": {
                "type": "local",
                "path": "/data/test",
                "file_pattern": "*.parquet",
                "enabled": True,
            }
        }
        response = client.post(
            "/admin/schema/sources",
            json=source_data,
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source_added"]["type"] == "local"
        assert data["source_added"]["path"] == "/data/test"

    def test_add_s3_source(self, client: TestClient, auth_headers: dict) -> None:
        """Test adding an S3 data source."""
        source_data = {
            "source": {
                "type": "s3",
                "path": "s3://mybucket/data",
                "file_pattern": "**/*.parquet",
                "enabled": True,
            }
        }
        response = client.post(
            "/admin/schema/sources",
            json=source_data,
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source_added"]["type"] == "s3"

    def test_add_invalid_source_type(self, client: TestClient, auth_headers: dict) -> None:
        """Test adding source with invalid type fails."""
        source_data = {
            "source": {
                "type": "invalid_type",
                "path": "/data/test",
            }
        }
        response = client.post(
            "/admin/schema/sources",
            json=source_data,
            headers=auth_headers,
        )
        assert response.status_code == 422  # Validation error


class TestGetSchemaContext:
    """Tests for GET /admin/schema/context endpoint."""

    def test_get_empty_context(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting schema context with no tables."""
        # First refresh to set last_refresh
        client.post("/admin/schema/refresh", headers=auth_headers)

        response = client.get("/admin/schema/context", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "No tables discovered" in data["context"]
        assert data["tables_count"] == 0

    def test_get_context_with_max_tables(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting schema context with max_tables parameter."""
        client.post("/admin/schema/refresh", headers=auth_headers)

        response = client.get(
            "/admin/schema/context",
            params={"max_tables": 5},
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestGetValidTables:
    """Tests for GET /admin/schema/tables endpoint."""

    def test_get_empty_tables(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting tables from empty registry."""
        client.post("/admin/schema/refresh", headers=auth_headers)

        response = client.get("/admin/schema/tables", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []


class TestGetTableColumns:
    """Tests for GET /admin/schema/tables/{table_name}/columns endpoint."""

    def test_table_not_found(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting columns for non-existent table."""
        client.post("/admin/schema/refresh", headers=auth_headers)

        response = client.get(
            "/admin/schema/tables/nonexistent/columns",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
