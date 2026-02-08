# Retail Insights Assistant - Setup Guide

## Prerequisites

- **Python 3.12+**
- **uv** (Python package manager) - [Install uv](https://docs.astral.sh/uv/)
- **Docker** (optional, for containerized deployment)
- **OpenAI API Key** for LLM-powered SQL generation

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/s1v4-d/nlsql-mas.git
cd nlsql-mas
```

### 2. Install Dependencies

```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (dev + ui)
uv sync --all-extras
```

### 3. Configure Environment

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Required
OPENAI_API_KEY=sk-your-openai-api-key

# Data Layer
DATA_PATH=./data/parquet
DUCKDB_MAX_MEMORY=4GB
DUCKDB_THREADS=4

# Optional - for production
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 4. Prepare Sample Data

If you have raw CSV data, convert to Parquet:

```bash
uv run python -c "
from retail_insights.engine.connector import DuckDBConnector
# Data conversion happens automatically on first query
"
```

Or place Parquet files directly in `./data/parquet/`.

### 5. Run the Application

**Option A: FastAPI Backend Only**

```bash
uv run uvicorn retail_insights.api.app:app --reload --host 0.0.0.0 --port 8000
```

Access API docs at: http://localhost:8000/docs

**Option B: Streamlit UI (includes backend)**

```bash
uv run streamlit run src/retail_insights/ui/app.py
```

Access UI at: http://localhost:8501

**Option C: Docker Compose (recommended for production-like setup)**

```bash
docker compose up --build
```

## Verify Installation

### Run Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Run Tests

```bash
# All tests with coverage
uv run pytest

# E2E tests only
uv run pytest tests/e2e/ -v

# Integration tests only
uv run pytest tests/integration/ -v
```

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | - | OpenAI API key (required) |
| `OPENAI_MODEL` | `gpt-4o` | Model for SQL generation |
| `DATA_PATH` | `./data/parquet` | Path to Parquet data files |
| `DUCKDB_MAX_MEMORY` | `4GB` | DuckDB memory limit |
| `DUCKDB_THREADS` | `4` | DuckDB thread count |
| `ENVIRONMENT` | `development` | development/staging/production |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `API_HOST` | `0.0.0.0` | API server host |
| `API_PORT` | `8000` | API server port |

## Directory Structure

```
nlsql-mas/
├── src/retail_insights/
│   ├── agents/         # LangGraph agents
│   ├── api/            # FastAPI routes
│   ├── core/           # Config, LLM, logging
│   ├── engine/         # DuckDB connector
│   ├── models/         # Pydantic schemas
│   └── ui/             # Streamlit app
├── tests/              # Test suite
├── data/               # Data files (gitignored)
├── infrastructure/     # Terraform modules
└── docs/               # Documentation
```

## Troubleshooting

### DuckDB Memory Errors

Increase memory limit in `.env`:
```env
DUCKDB_MAX_MEMORY=8GB
```

### OpenAI Rate Limits

The system includes automatic retry with exponential backoff. For high-volume usage, consider:
- Enabling Redis caching
- Reducing `temperature` for more consistent SQL

### Schema Not Found

Ensure Parquet files exist in `DATA_PATH` and run:
```bash
curl -X POST http://localhost:8000/admin/schema/refresh
```

## Next Steps

- [API Documentation](./API.md) - Full API reference
- [Architecture Overview](./architecture/HLD.md) - System design
- [Contributing Guide](./CONTRIBUTING.md) - Development workflow
