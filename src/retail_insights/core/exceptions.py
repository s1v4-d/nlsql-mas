"""Custom exceptions for the Retail Insights Assistant."""

from typing import Any


class RetailInsightsError(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(RetailInsightsError):
    """Raised when SQL validation fails."""

    def __init__(
        self,
        message: str,
        errors: list[str] | None = None,
        sql: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details={"errors": errors or [], "sql": sql},
        )
        self.errors = errors or []
        self.sql = sql


class SQLGenerationError(RetailInsightsError):
    """Raised when SQL generation fails after all retries."""

    def __init__(
        self,
        message: str,
        user_query: str,
        attempts: int,
        last_error: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="SQL_GENERATION_ERROR",
            details={
                "user_query": user_query,
                "attempts": attempts,
                "last_error": last_error,
            },
        )
        self.user_query = user_query
        self.attempts = attempts
        self.last_error = last_error


class ExecutionError(RetailInsightsError):
    """Raised when query execution fails."""

    def __init__(
        self,
        message: str,
        sql: str,
        original_error: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="EXECUTION_ERROR",
            details={"sql": sql, "original_error": original_error},
        )
        self.sql = sql
        self.original_error = original_error


class SchemaError(RetailInsightsError):
    """Raised when schema registry operations fail."""

    def __init__(
        self,
        message: str,
        source_type: str | None = None,
        source_path: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="SCHEMA_ERROR",
            details={"source_type": source_type, "source_path": source_path},
        )
        self.source_type = source_type
        self.source_path = source_path


class ConfigurationError(RetailInsightsError):
    """Raised when configuration is invalid or missing."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details={"config_key": config_key},
        )
        self.config_key = config_key


class RateLimitError(RetailInsightsError):
    """Raised when rate limits are exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_ERROR",
            details={"retry_after": retry_after},
        )
        self.retry_after = retry_after


class AuthenticationError(RetailInsightsError):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str = "Authentication failed",
    ) -> None:
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
        )
