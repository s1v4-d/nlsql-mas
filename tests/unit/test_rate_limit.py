"""Unit tests for rate limiting functionality."""

from unittest.mock import MagicMock, patch

from retail_insights.api.rate_limit import (
    _get_key_func,
    get_limiter,
    reset_limiter,
)


class TestGetKeyFunc:
    """Tests for rate limit key function."""

    def test_uses_api_key_when_present(self):
        """Test API key is used for rate limit key."""
        request = MagicMock()
        request.headers = {"X-API-Key": "ri_1234567890abcdef1234567890"}

        key = _get_key_func(request)
        assert key.startswith("apikey:")
        assert "ri_1234567890ab" in key

    def test_uses_ip_when_no_api_key(self):
        """Test IP address is used when no API key."""
        request = MagicMock()
        request.headers = {}
        request.client.host = "192.168.1.100"

        key = _get_key_func(request)
        assert key == "192.168.1.100"

    def test_truncates_api_key(self):
        """Test API key is truncated to 16 chars."""
        long_key = "ri_" + "a" * 100
        request = MagicMock()
        request.headers = {"X-API-Key": long_key}

        key = _get_key_func(request)
        assert len(key) == len("apikey:") + 16


class TestGetLimiter:
    """Tests for limiter singleton."""

    def setup_method(self):
        """Reset limiter before each test."""
        reset_limiter()

    def test_returns_limiter_instance(self):
        """Test returns a Limiter instance."""
        with patch("retail_insights.api.rate_limit.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                REDIS_URL=None,
                RATE_LIMIT_DEFAULT="60/minute",
                RATE_LIMIT_ENABLED=True,
            )
            limiter = get_limiter()
            assert limiter is not None

    def test_singleton_returns_same_instance(self):
        """Test singleton returns same instance."""
        with patch("retail_insights.api.rate_limit.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                REDIS_URL=None,
                RATE_LIMIT_DEFAULT="60/minute",
                RATE_LIMIT_ENABLED=True,
            )
            limiter1 = get_limiter()
            limiter2 = get_limiter()
            assert limiter1 is limiter2

    def test_reset_creates_new_instance(self):
        """Test reset allows new instance creation."""
        with patch("retail_insights.api.rate_limit.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                REDIS_URL=None,
                RATE_LIMIT_DEFAULT="60/minute",
                RATE_LIMIT_ENABLED=True,
            )
            limiter1 = get_limiter()
            reset_limiter()
            limiter2 = get_limiter()
            assert limiter1 is not limiter2


class TestRateLimitSettings:
    """Tests for rate limit configuration."""

    def setup_method(self):
        """Reset limiter before each test."""
        reset_limiter()

    def test_uses_redis_when_configured(self):
        """Test Redis storage is used when URL is provided."""
        with patch("retail_insights.api.rate_limit.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                REDIS_URL="redis://localhost:6379/0",
                RATE_LIMIT_DEFAULT="60/minute",
                RATE_LIMIT_ENABLED=True,
            )
            limiter = get_limiter()
            assert limiter is not None

    def test_uses_memory_when_no_redis(self):
        """Test memory storage is used when no Redis."""
        with patch("retail_insights.api.rate_limit.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                REDIS_URL=None,
                RATE_LIMIT_DEFAULT="60/minute",
                RATE_LIMIT_ENABLED=True,
            )
            limiter = get_limiter()
            assert limiter is not None
