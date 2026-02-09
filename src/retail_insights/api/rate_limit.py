"""Rate limiting for FastAPI endpoints using SlowAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from retail_insights.core.config import get_settings

if TYPE_CHECKING:
    from retail_insights.core.config import Settings

_limiter: Limiter | None = None


def _get_key_func(request: Request) -> str:
    """Get rate limit key from API key or IP address.

    Uses API key if present for per-user limits, otherwise falls back to IP.

    Args:
        request: The incoming request.

    Returns:
        The rate limit key (API key or client IP).
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key[:16]}"
    return get_remote_address(request)


def get_limiter(settings: Settings | None = None) -> Limiter:
    """Get or create the rate limiter singleton.

    Args:
        settings: Application settings.

    Returns:
        Configured Limiter instance.
    """
    global _limiter
    if _limiter is not None:
        return _limiter

    settings = settings or get_settings()

    storage_uri = "memory://"
    if settings.REDIS_URL:
        storage_uri = settings.REDIS_URL

    _limiter = Limiter(
        key_func=_get_key_func,
        default_limits=[settings.RATE_LIMIT_DEFAULT],
        storage_uri=storage_uri,
        enabled=settings.RATE_LIMIT_ENABLED,
        headers_enabled=True,
        in_memory_fallback_enabled=True,
        swallow_errors=True,
    )

    return _limiter


def reset_limiter() -> None:
    """Reset the limiter singleton (for testing)."""
    global _limiter
    _limiter = None


def get_rate_limit_exceeded_handler():
    """Get rate limit exceeded exception handler.

    Returns:
        FastAPI exception handler for RateLimitExceeded.
    """
    from fastapi import status
    from fastapi.responses import JSONResponse

    from retail_insights.api.dependencies import request_id_ctx

    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        retry_after = getattr(exc, "retry_after", 60)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded: {exc.detail}",
                "request_id": request_id_ctx.get(),
            },
            headers={"Retry-After": str(retry_after)},
        )

    return rate_limit_exceeded_handler


class _LazyLimiter:
    """Lazy limiter proxy to defer initialization until first use."""

    _instance: Limiter | None = None

    def __getattr__(self, name):
        if self._instance is None:
            self._instance = get_limiter()
        return getattr(self._instance, name)


limiter = _LazyLimiter()
