"""Unit tests for core configuration."""

import os
from unittest.mock import patch

from retail_insights.core.config import Settings, get_settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "DEBUG": "false",
                "LOG_LEVEL": "INFO",
                "ENVIRONMENT": "development",
            },
            clear=False,
        ):
            get_settings.cache_clear()
            settings = Settings()
            assert settings.APP_NAME == "Retail Insights Assistant"
            assert settings.DEBUG is False
            assert settings.LOG_LEVEL == "INFO"
            assert settings.ENVIRONMENT == "development"
            assert settings.API_PORT == 8000
            assert settings.OPENAI_MODEL == "gpt-4o"
            assert settings.OPENAI_TEMPERATURE == 0.0

    def test_environment_override(self) -> None:
        """Test that environment variables override defaults."""
        env_vars = {
            "OPENAI_API_KEY": "test-key",
            "DEBUG": "true",
            "LOG_LEVEL": "DEBUG",
            "ENVIRONMENT": "production",
            "API_PORT": "9000",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings()
            assert settings.DEBUG is True
            assert settings.LOG_LEVEL == "DEBUG"
            assert settings.ENVIRONMENT == "production"
            assert settings.API_PORT == 9000

    def test_is_production(self) -> None:
        """Test is_production property."""
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test", "ENVIRONMENT": "production"},
            clear=False,
        ):
            settings = Settings()
            assert settings.is_production is True

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test", "ENVIRONMENT": "development"},
            clear=False,
        ):
            settings = Settings()
            assert settings.is_production is False

    def test_database_configured(self, monkeypatch, tmp_path) -> None:
        """Test database_configured property."""
        # Create a temporary empty env file to avoid loading real env files
        empty_env = tmp_path / ".env"
        empty_env.write_text("")

        # Temporarily change working directory to tmp_path to avoid loading dev.env
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()
        settings = Settings(_env_file=str(empty_env))
        assert settings.database_configured is False

        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        get_settings.cache_clear()
        settings = Settings(_env_file=str(empty_env))
        assert settings.database_configured is True

    def test_cors_origins_parsing(self) -> None:
        """Test CORS origins parsing from JSON array string."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test",
                "CORS_ORIGINS": '["http://localhost:3000", "http://localhost:8080"]',
            },
            clear=False,
        ):
            settings = Settings()
            assert len(settings.CORS_ORIGINS) == 2
            assert "http://localhost:3000" in settings.CORS_ORIGINS

    def test_aws_configured(self) -> None:
        """Test aws_configured property."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test",
                "AWS_ACCESS_KEY_ID": "",
                "AWS_SECRET_ACCESS_KEY": "",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.aws_configured is False

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test",
                "AWS_ACCESS_KEY_ID": "AKIAXXXXXXX",
                "AWS_SECRET_ACCESS_KEY": "secret123",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.aws_configured is True

    def test_secret_str_handling(self) -> None:
        """Test that secrets are properly handled."""
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-secret-key"},
            clear=False,
        ):
            settings = Settings()
            # SecretStr should not expose value in string representation
            assert "sk-secret-key" not in str(settings.OPENAI_API_KEY)
            # But should be accessible via get_secret_value()
            assert settings.OPENAI_API_KEY.get_secret_value() == "sk-secret-key"


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_cached(self) -> None:
        """Test that get_settings returns cached instance."""
        # Clear the cache first
        get_settings.cache_clear()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=False):
            settings1 = get_settings()
            settings2 = get_settings()
            assert settings1 is settings2
