"""API authentication and authorization."""

from __future__ import annotations

import hmac
import secrets
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from retail_insights.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


class ApiKeyScope(StrEnum):
    """API key permission scopes."""

    USER = "user"
    ADMIN = "admin"


class AuthenticatedUser(BaseModel):
    """Authenticated user info extracted from API key."""

    scope: ApiKeyScope
    key_prefix: str


api_key_header = APIKeyHeader(
    name="X-API-Key",
    description="API key for authentication. Use your user key for regular access or admin key for admin endpoints.",
    auto_error=False,
)


def _constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _get_key_prefix(key: str, length: int = 8) -> str:
    """Get prefix of key for logging (safe, doesn't expose full key)."""
    return key[:length] + "..." if len(key) > length else key


def verify_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
    settings: SettingsDep = None,  # type: ignore[assignment]
) -> AuthenticatedUser | None:
    """Verify API key and return authenticated user with scope.

    Checks the provided key against both user and admin keys.
    Returns AuthenticatedUser with appropriate scope based on which key matched.

    Args:
        request: The incoming request.
        api_key: API key from header.
        settings: Application settings.

    Returns:
        AuthenticatedUser with scope, or None if auth is disabled.

    Raises:
        HTTPException: If authentication fails.
    """
    if not settings.AUTH_ENABLED:
        return None

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if _constant_time_compare(api_key, settings.ADMIN_API_KEY):
        return AuthenticatedUser(
            scope=ApiKeyScope.ADMIN,
            key_prefix=_get_key_prefix(api_key),
        )

    configured_user_key = settings.API_KEY
    if configured_user_key and _constant_time_compare(
        api_key, configured_user_key.get_secret_value()
    ):
        return AuthenticatedUser(
            scope=ApiKeyScope.USER,
            key_prefix=_get_key_prefix(api_key),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_admin(
    api_key: str | None = Security(api_key_header),
    settings: SettingsDep = None,  # type: ignore[assignment]
) -> AuthenticatedUser:
    """Require admin API key for protected endpoints.

    Admin routes always require authentication, regardless of AUTH_ENABLED setting.

    Args:
        api_key: API key from header.
        settings: Application settings.

    Returns:
        The authenticated admin user.

    Raises:
        HTTPException: If admin authentication fails.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key required. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if _constant_time_compare(api_key, settings.ADMIN_API_KEY):
        return AuthenticatedUser(
            scope=ApiKeyScope.ADMIN,
            key_prefix=_get_key_prefix(api_key),
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid admin API key",
    )


def optional_api_key(
    api_key: str | None = Security(api_key_header),
    settings: SettingsDep = None,  # type: ignore[assignment]
) -> AuthenticatedUser | None:
    """Get authenticated user if API key provided (for analytics/logging).

    Does not enforce authentication, just captures the user info if valid key present.

    Args:
        api_key: API key from header.
        settings: Application settings.

    Returns:
        AuthenticatedUser if valid key, None otherwise.
    """
    if not api_key:
        return None

    if _constant_time_compare(api_key, settings.ADMIN_API_KEY):
        return AuthenticatedUser(
            scope=ApiKeyScope.ADMIN,
            key_prefix=_get_key_prefix(api_key),
        )

    configured_user_key = settings.API_KEY
    if configured_user_key and _constant_time_compare(
        api_key, configured_user_key.get_secret_value()
    ):
        return AuthenticatedUser(
            scope=ApiKeyScope.USER,
            key_prefix=_get_key_prefix(api_key),
        )

    return None


def generate_api_key(prefix: str = "ri") -> str:
    """Generate a secure random API key.

    Args:
        prefix: Key prefix for identification.

    Returns:
        A secure random API key like 'ri_a1b2c3d4e5f6g7h8'.
    """
    token = secrets.token_urlsafe(24)
    return f"{prefix}_{token}"


ApiKeyDep = Annotated[AuthenticatedUser | None, Depends(verify_api_key)]
AdminKeyDep = Annotated[AuthenticatedUser, Depends(require_admin)]
OptionalApiKeyDep = Annotated[AuthenticatedUser | None, Depends(optional_api_key)]

# Backward compatibility aliases
require_admin_key = require_admin
