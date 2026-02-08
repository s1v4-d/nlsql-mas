# =============================================================================
# Retail Insights FastAPI - Production Dockerfile
# =============================================================================
# Multi-stage build with uv for optimal layer caching and small final image.
# Uses Python 3.12 on Debian Bookworm (slim variant).

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and build the project
# -----------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# uv optimization flags
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies first (cached unless pyproject.toml/uv.lock change)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy source and install project
COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# -----------------------------------------------------------------------------
# Stage 2: Development - Full source with hot reload support
# -----------------------------------------------------------------------------
FROM builder AS development

# Keep dev dependencies for testing
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "retail_insights.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# -----------------------------------------------------------------------------
# Stage 3: Production - Minimal runtime image
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS production

# Python settings for production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/app/.venv/bin:$PATH"

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --system --gid 999 appuser \
    && useradd --system --gid 999 --uid 999 --no-create-home --shell /sbin/nologin appuser

WORKDIR /app

# Copy only the virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Switch to non-root user
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

# Production server with proxy-headers for TLS termination
CMD ["uvicorn", "retail_insights.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
