"""API authentication and authorization."""

from __future__ import annotations

import hmac
import secrets
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from retail_insights.core.config import get_settings

if TYPE_CHECKING:
    from retail_insights.core.config import Settings


class ApiKeyScope(StrEnum):
    """API key permission scopes."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str | None:
    """Verify API key if authentication is enabled.

    Args:
        request: The incoming request.
        api_key: API key from header.
        settings: Application settings.

    Returns:
        The validated API key or None if auth is disabled.

    Raises:
        HTTPException: If authentication fails.
    """
    if not settings.AUTH_ENABLED:
        return None

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    configured_key = settings.API_KEY
    if configured_key is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured on server",
        )

    if not _constant_time_compare(api_key, configured_key.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key


def require_admin_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Require admin API key for protected endpoints.

    Args:
        request: The incoming request.
        api_key: API key from header.
        settings: Application settings.

    Returns:
        The validated admin API key.

    Raises:
        HTTPException: If admin authentication fails.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not _constant_time_compare(api_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key",
        )

    return api_key


def optional_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str | None:
    """Get API key if provided (for analytics/logging).

    Does not enforce authentication, just captures the key if present.

    Args:
        api_key: API key from header.
        settings: Application settings.

    Returns:
        The API key if valid, None otherwise.
    """
    if not api_key:
        return None

    configured_key = settings.API_KEY
    if configured_key and _constant_time_compare(api_key, configured_key.get_secret_value()):
        return api_key

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


ApiKeyDep = Annotated[str | None, Depends(verify_api_key)]
AdminKeyDep = Annotated[str, Depends(require_admin_key)]
OptionalApiKeyDep = Annotated[str | None, Depends(optional_api_key)]
