"""Application configuration using Pydantic Settings with multi-file support."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Pydantic-settings natively loads from multiple .env files in priority order.
    Later files override earlier ones. Secrets use SecretStr for security.

    Priority (lowest to highest):
    1. .env (base defaults)
    2. env-files/dev.env (development overrides)
    3. env-files/secrets/secrets.env (secrets, never committed)
    4. OS environment variables (highest priority)
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "env-files/dev.env", "env-files/secrets/secrets.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Retail Insights Assistant"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 1
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    API_KEY: SecretStr | None = None
    ADMIN_API_KEY: str = Field(
        default="dev-admin-key",
        description="API key for admin endpoints",
    )

    # OpenAI Configuration
    OPENAI_API_KEY: SecretStr = Field(..., description="OpenAI API key")
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)
    OPENAI_MAX_TOKENS: int = Field(default=4096, ge=100, le=128000)
    OPENAI_TIMEOUT: int = Field(default=60, ge=10, le=300)

    # Database Configuration (PostgreSQL for checkpoints/vectors)
    DATABASE_URL: str | None = Field(
        default=None,
        description="PostgreSQL connection URL for checkpoints",
    )

    # Redis Configuration
    REDIS_URL: str | None = Field(
        default=None,
        description="Redis connection URL for caching",
    )
    REDIS_TTL_SECONDS: int = Field(default=3600, ge=60)

    # Query Cache Configuration
    CACHE_ENABLED: bool = Field(default=True, description="Enable query caching")
    CACHE_TTL_SECONDS: int = Field(default=300, ge=30, description="Cache TTL in seconds")
    CACHE_L1_TTL_SECONDS: int = Field(default=60, ge=10, description="In-memory cache TTL")
    CACHE_L1_MAX_SIZE: int = Field(default=100, ge=10, description="In-memory cache max entries")

    # AWS Configuration
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: SecretStr | None = None
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str | None = None

    # DuckDB Configuration
    DUCKDB_MEMORY_LIMIT: str = "4GB"
    DUCKDB_THREADS: int = Field(default=4, ge=1, le=64)

    # Data Paths
    S3_DATA_PATH: str = Field(
        default="s3://retail-insights/data",
        description="S3 path prefix for Parquet data",
    )
    LOCAL_DATA_PATH: str = Field(
        default="data/parquet",
        description="Local path for Parquet files",
    )

    # Schema Registry
    SCHEMA_CACHE_TTL: int = Field(
        default=300,
        ge=60,
        description="Schema cache TTL in seconds (default 5 min)",
    )

    # Agent Configuration
    MAX_RETRY_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    QUERY_RESULT_LIMIT: int = Field(default=100, ge=1, le=10000)

    # Observability
    OTEL_ENABLED: bool = Field(default=False, description="Enable OpenTelemetry")
    OTEL_SERVICE_NAME: str = Field(default="retail-insights")
    OTEL_EXPORTER_TYPE: Literal["otlp", "xray", "console", "none"] = "none"
    OTEL_EXPORTER_ENDPOINT: str = Field(default="http://localhost:4317")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_DEFAULT: str = Field(default="60/minute", description="Default rate limit")
    RATE_LIMIT_QUERY: str = Field(default="30/minute", description="Rate limit for query endpoints")
    RATE_LIMIT_ADMIN: str = Field(default="10/minute", description="Rate limit for admin endpoints")

    # Security
    AUTH_ENABLED: bool = Field(default=False, description="Enable API key authentication")
    SECURITY_HEADERS_ENABLED: bool = Field(default=True, description="Enable security headers")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == "production"

    @property
    def database_configured(self) -> bool:
        """Check if database is configured."""
        return self.DATABASE_URL is not None

    @property
    def redis_configured(self) -> bool:
        """Check if Redis is configured."""
        return self.REDIS_URL is not None

    @property
    def cache_configured(self) -> bool:
        """Check if caching is enabled and configured."""
        return self.CACHE_ENABLED

    @property
    def aws_configured(self) -> bool:
        """Check if AWS credentials are configured."""
        return self.AWS_ACCESS_KEY_ID is not None and self.AWS_SECRET_ACCESS_KEY is not None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
