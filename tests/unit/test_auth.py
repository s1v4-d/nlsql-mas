"""Unit tests for API security features."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from retail_insights.api.auth import (
    ApiKeyScope,
    AuthenticatedUser,
    _constant_time_compare,
    generate_api_key,
    optional_api_key,
    require_admin,
    verify_api_key,
)


class TestConstantTimeCompare:
    """Tests for constant-time string comparison."""

    def test_equal_strings(self):
        """Test matching strings return True."""
        assert _constant_time_compare("test123", "test123") is True

    def test_unequal_strings(self):
        """Test non-matching strings return False."""
        assert _constant_time_compare("test123", "test456") is False

    def test_empty_strings(self):
        """Test empty strings comparison."""
        assert _constant_time_compare("", "") is True
        assert _constant_time_compare("", "test") is False

    def test_different_lengths(self):
        """Test strings of different lengths."""
        assert _constant_time_compare("short", "longer_string") is False


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_default_prefix(self):
        """Test default prefix is 'ri'."""
        key = generate_api_key()
        assert key.startswith("ri_")

    def test_custom_prefix(self):
        """Test custom prefix is used."""
        key = generate_api_key(prefix="custom")
        assert key.startswith("custom_")

    def test_unique_keys(self):
        """Test generated keys are unique."""
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100

    def test_key_length(self):
        """Test key has reasonable length."""
        key = generate_api_key()
        assert len(key) > 20


class TestApiKeyScope:
    """Tests for API key scope enum."""

    def test_scope_values(self):
        """Test all scope values exist."""
        assert ApiKeyScope.USER == "user"
        assert ApiKeyScope.ADMIN == "admin"


class TestVerifyApiKey:
    """Tests for API key verification."""

    def test_auth_disabled_returns_none(self):
        """Test returns None when auth is disabled."""
        request = MagicMock()
        settings = MagicMock(AUTH_ENABLED=False)

        result = verify_api_key(request, api_key="any-key", settings=settings)
        assert result is None

    def test_missing_key_raises_401(self):
        """Test missing API key raises 401."""
        request = MagicMock()
        settings = MagicMock(AUTH_ENABLED=True)

        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(request, api_key=None, settings=settings)
        assert exc_info.value.status_code == 401

    def test_invalid_key_raises_401(self):
        """Test invalid API key raises 401."""
        request = MagicMock()
        settings = MagicMock(
            AUTH_ENABLED=True,
            API_KEY=SecretStr("user-key"),
            ADMIN_API_KEY="admin-key",
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(request, api_key="wrong-key", settings=settings)
        assert exc_info.value.status_code == 401

    def test_admin_key_returns_admin_user(self):
        """Test admin API key returns user with admin scope."""
        request = MagicMock()
        settings = MagicMock(
            AUTH_ENABLED=True,
            API_KEY=SecretStr("user-key"),
            ADMIN_API_KEY="admin-key",
        )

        result = verify_api_key(request, api_key="admin-key", settings=settings)
        assert isinstance(result, AuthenticatedUser)
        assert result.scope == ApiKeyScope.ADMIN

    def test_user_key_returns_user(self):
        """Test user API key returns user with user scope."""
        request = MagicMock()
        settings = MagicMock(
            AUTH_ENABLED=True,
            API_KEY=SecretStr("user-key"),
            ADMIN_API_KEY="admin-key",
        )

        result = verify_api_key(request, api_key="user-key", settings=settings)
        assert isinstance(result, AuthenticatedUser)
        assert result.scope == ApiKeyScope.USER


class TestRequireAdmin:
    """Tests for admin access requirement."""

    def test_missing_key_raises_401(self):
        """Test missing admin key raises 401."""
        settings = MagicMock(ADMIN_API_KEY="admin-key")

        with pytest.raises(HTTPException) as exc_info:
            require_admin(api_key=None, settings=settings)
        assert exc_info.value.status_code == 401

    def test_invalid_key_raises_403(self):
        """Test invalid admin key raises 403."""
        settings = MagicMock(ADMIN_API_KEY="admin-key")

        with pytest.raises(HTTPException) as exc_info:
            require_admin(api_key="wrong-key", settings=settings)
        assert exc_info.value.status_code == 403

    def test_valid_admin_key_returns_admin_user(self):
        """Test valid admin key returns authenticated admin user."""
        settings = MagicMock(ADMIN_API_KEY="admin-key")

        result = require_admin(api_key="admin-key", settings=settings)
        assert isinstance(result, AuthenticatedUser)
        assert result.scope == ApiKeyScope.ADMIN


class TestOptionalApiKey:
    """Tests for optional API key capture."""

    def test_no_key_returns_none(self):
        """Test missing key returns None."""
        settings = MagicMock(API_KEY=None, ADMIN_API_KEY="admin-key")
        result = optional_api_key(api_key=None, settings=settings)
        assert result is None

    def test_invalid_key_returns_none(self):
        """Test invalid key returns None."""
        settings = MagicMock(API_KEY=SecretStr("user-key"), ADMIN_API_KEY="admin-key")
        result = optional_api_key(api_key="wrong-key", settings=settings)
        assert result is None

    def test_valid_user_key_returns_user(self):
        """Test valid user key returns authenticated user."""
        settings = MagicMock(API_KEY=SecretStr("user-key"), ADMIN_API_KEY="admin-key")
        result = optional_api_key(api_key="user-key", settings=settings)
        assert isinstance(result, AuthenticatedUser)
        assert result.scope == ApiKeyScope.USER

    def test_valid_admin_key_returns_admin(self):
        """Test valid admin key returns authenticated admin."""
        settings = MagicMock(API_KEY=SecretStr("user-key"), ADMIN_API_KEY="admin-key")
        result = optional_api_key(api_key="admin-key", settings=settings)
        assert isinstance(result, AuthenticatedUser)
        assert result.scope == ApiKeyScope.ADMIN
