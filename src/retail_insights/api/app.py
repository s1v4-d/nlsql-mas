"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from retail_insights.api.dependencies import request_id_ctx
from retail_insights.api.routes.admin import router as admin_router
from retail_insights.api.routes.query import router as query_router
from retail_insights.core.config import get_settings
from retail_insights.core.exceptions import (
    AuthenticationError,
    ExecutionError,
    RateLimitError,
    RetailInsightsError,
    SQLGenerationError,
    ValidationError,
)
from retail_insights.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events.

    Initializes:
    - Settings configuration
    - Schema registry for database metadata
    - LangGraph workflow with checkpointer
    - OpenTelemetry instrumentation
    """
    settings = get_settings()
    app.state.settings = settings
    logger.info("app_starting", environment=settings.ENVIRONMENT)

    from retail_insights.core.telemetry import configure_telemetry

    configure_telemetry(app, settings)

    from retail_insights.engine.schema_registry import get_schema_registry

    schema_registry = get_schema_registry(settings=settings)
    app.state.schema_registry = schema_registry
    logger.info("schema_registry_initialized", table_count=len(schema_registry.get_table_info()))

    from retail_insights.agents.graph import build_graph, get_memory_checkpointer

    checkpointer = get_memory_checkpointer()
    graph = build_graph(checkpointer=checkpointer)
    app.state.graph = graph
    app.state.checkpointer = checkpointer
    logger.info("langgraph_initialized", checkpointer_type="memory")

    yield

    logger.info("app_shutdown")


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers for application errors."""

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        """Handle SQL validation errors with 422 status."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id_ctx.get(),
            },
        )

    @app.exception_handler(SQLGenerationError)
    async def sql_generation_error_handler(
        request: Request, exc: SQLGenerationError
    ) -> JSONResponse:
        """Handle SQL generation failures after retries."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id_ctx.get(),
            },
        )

    @app.exception_handler(ExecutionError)
    async def execution_error_handler(request: Request, exc: ExecutionError) -> JSONResponse:
        """Handle query execution failures."""
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "details": {"sql": exc.sql} if exc.sql else {},
                "request_id": request_id_ctx.get(),
            },
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitError) -> JSONResponse:
        """Handle rate limit exceeded errors."""
        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "request_id": request_id_ctx.get(),
            },
            headers=headers,
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        """Handle authentication failures."""
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "request_id": request_id_ctx.get(),
            },
        )

    @app.exception_handler(RetailInsightsError)
    async def retail_insights_error_handler(
        request: Request, exc: RetailInsightsError
    ) -> JSONResponse:
        """Handle generic application errors."""
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "request_id": request_id_ctx.get(),
            },
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="GenAI-powered Retail Insights Assistant with NL-to-SQL capabilities",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    from slowapi.errors import RateLimitExceeded

    from retail_insights.api.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
    from retail_insights.api.rate_limit import get_limiter, get_rate_limit_exceeded_handler

    limiter = get_limiter(settings)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, get_rate_limit_exceeded_handler())

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(admin_router)
    app.include_router(query_router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, Any]:
        """Basic health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "request_id": request_id_ctx.get(),
        }

    @app.get("/ready", tags=["health"])
    async def readiness_check() -> dict[str, Any]:
        """Readiness check for Kubernetes.

        Verifies schema registry is initialized and graph is ready.
        """
        schema_ready = hasattr(app.state, "schema_registry")
        graph_ready = hasattr(app.state, "graph")

        if schema_ready and graph_ready:
            return {"status": "ready", "request_id": request_id_ctx.get()}

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "schema_registry": schema_ready,
                "graph": graph_ready,
                "request_id": request_id_ctx.get(),
            },
        )

    return app


# Lazy-loaded app for uvicorn deployment
# Usage: uvicorn retail_insights.api.app:app --host 0.0.0.0
# Or with factory: uvicorn retail_insights.api.app:create_app --factory
def __getattr__(name: str):
    """Lazy load the app when accessed.

    This prevents settings validation from running at import time,
    allowing tests to mock environment variables before app creation.
    """
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
