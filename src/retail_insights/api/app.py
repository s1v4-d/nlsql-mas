"""FastAPI application entry point."""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events.

    Initializes:
    - Settings configuration
    - Schema registry for database metadata
    - LangGraph workflow with checkpointer
    """
    # Startup
    settings = get_settings()
    app.state.settings = settings

    # Initialize schema registry on startup
    from retail_insights.engine.schema_registry import get_schema_registry

    schema_registry = get_schema_registry(settings=settings)
    app.state.schema_registry = schema_registry
    logger.info("Schema registry initialized with %d tables", len(schema_registry.get_table_info()))

    # Initialize LangGraph workflow
    from retail_insights.agents.graph import build_graph, get_memory_checkpointer

    checkpointer = get_memory_checkpointer()
    graph = build_graph(checkpointer=checkpointer)
    app.state.graph = graph
    app.state.checkpointer = checkpointer
    logger.info("LangGraph workflow initialized with memory checkpointer")

    yield

    # Shutdown
    logger.info("Application shutdown complete")


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
    async def sql_generation_error_handler(request: Request, exc: SQLGenerationError) -> JSONResponse:
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
    async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
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
    async def retail_insights_error_handler(request: Request, exc: RetailInsightsError) -> JSONResponse:
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

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        """Add request ID to each request for tracing."""
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"

        logger.info(
            "Request completed",
            extra={
                "request_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Include routers
    app.include_router(admin_router)
    app.include_router(query_router)

    # Health endpoints
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
