"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from retail_insights.api.routes.admin import router as admin_router
from retail_insights.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    settings = get_settings()
    app.state.settings = settings

    # Initialize schema registry on startup
    from retail_insights.engine.schema_registry import get_schema_registry

    get_schema_registry(settings=settings)

    yield

    # Shutdown
    pass


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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(admin_router)

    # Health endpoints
    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, Any]:
        """Basic health check endpoint."""
        return {"status": "healthy", "version": settings.APP_VERSION}

    @app.get("/ready", tags=["health"])
    async def readiness_check() -> dict[str, Any]:
        """Readiness check for Kubernetes."""
        # Check database connectivity when available
        return {"status": "ready"}

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
