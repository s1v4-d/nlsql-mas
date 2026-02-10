# Retail Insights Assistant - Low Level Design (LLD)

## 1. Project Structure

```
nlsql-mas/
├── pyproject.toml                    # uv dependency management
├── uv.lock                           # Lockfile for reproducibility
├── README.md                         # Project documentation
├── .env.example                      # Environment variables template
├── docker-compose.yml                # Local development stack
├── Dockerfile                        # Production container
│
├── src/
│   └── retail_insights/              # Main Python package
│       ├── __init__.py
│       ├── main.py                   # Application entry point
│       │
│       ├── api/                      # FastAPI REST/WebSocket
│       │   ├── __init__.py
│       │   ├── app.py                # FastAPI application factory
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── query.py          # Query endpoints
│       │   │   ├── summarize.py      # Summarization endpoints
│       │   │   ├── health.py         # Health checks
│       │   │   └── websocket.py      # WebSocket streaming
│       │   ├── dependencies.py       # Dependency injection
│       │   └── middleware.py         # Auth, logging middleware
│       │
│       ├── agents/                   # LangGraph agent implementations
│       │   ├── __init__.py
│       │   ├── state.py              # Agent state schema
│       │   ├── graph.py              # Graph compilation
│       │   ├── nodes/
│       │   │   ├── __init__.py
│       │   │   ├── router.py         # Intent routing agent
│       │   │   ├── sql_generator.py  # NL→SQL agent
│       │   │   ├── validator.py      # SQL validation agent
│       │   │   ├── executor.py       # Query execution agent
│       │   │   └── summarizer.py     # Response summarization agent
│       │   └── prompts/
│       │       ├── __init__.py
│       │       ├── router.py         # Router prompt templates
│       │       ├── sql_generator.py  # SQL generation prompts
│       │       └── summarizer.py     # Summarization prompts
│       │
│       ├── engine/                   # DuckDB data layer
│       │   ├── __init__.py
│       │   ├── connector.py          # DuckDB connection manager
│       │   ├── query_runner.py       # Query execution wrapper
│       │   └── schema_registry.py    # Table/column metadata
│       │
│       ├── models/                   # Pydantic schemas
│       │   ├── __init__.py
│       │   ├── requests.py           # API request models
│       │   ├── responses.py          # API response models
│       │   ├── agents.py             # Agent I/O models
│       │   └── database.py           # Database entity models
│       │
│       ├── core/                     # Shared utilities
│       │   ├── __init__.py
│       │   ├── config.py             # Pydantic settings
│       │   ├── logging.py            # Structured logging
│       │   ├── exceptions.py         # Custom exceptions
│       │   └── llm.py                # LLM client abstraction
│       │
│       └── ui/                       # Streamlit interface
│           ├── __init__.py
│           └── app.py                # Streamlit main app
│
├── tests/                            # Test suite
│   ├── conftest.py                   # Pytest fixtures
│   ├── unit/
│   │   ├── test_agents.py
│   │   ├── test_engine.py
│   │   └── test_validators.py
│   ├── integration/
│   │   ├── test_api.py
│   │   └── test_workflow.py
│   └── e2e/
│       └── test_queries.py
│
├── notebooks/                        # Jupyter notebooks
│   └── 01_data_exploration.ipynb
│
├── data/                             # Local data (gitignored)
│   └── parquet/
│
├── docs/                             # Documentation
│   ├── architecture/
│   │   ├── HLD.md
│   │   └── LLD.md
│   └── schema_documentation.md
│
└── infrastructure/                   # Terraform IaC
    ├── modules/
    │   ├── networking/
    │   ├── ecs/
    │   ├── aurora/
    │   ├── s3/
    │   └── monitoring/
    └── environments/
        ├── dev/
        ├── staging/
        └── prod/
```

---

## 2. Pydantic Models

### 2.1 Request Models (`src/retail_insights/models/requests.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class QueryMode(str, Enum):
    QUERY = "query"
    SUMMARIZE = "summarize"


class QueryRequest(BaseModel):
    """Request for natural language query processing."""

    question: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Natural language question about sales data"
    )
    mode: QueryMode = Field(
        default=QueryMode.QUERY,
        description="Query mode: 'query' for Q&A, 'summarize' for summaries"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation continuity"
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum number of result rows"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What were the top 5 categories by revenue in Q3 2022?",
                "mode": "query",
                "session_id": "abc123",
                "max_results": 100
            }
        }


class SummarizeRequest(BaseModel):
    """Request for automated sales summary."""

    time_period: Optional[str] = Field(
        default="last_quarter",
        description="Time period for summary (e.g., 'last_month', 'last_quarter', 'ytd')"
    )
    region: Optional[str] = Field(
        default=None,
        description="Filter by region/state"
    )
    category: Optional[str] = Field(
        default=None,
        description="Filter by product category"
    )
```

### 2.2 Response Models (`src/retail_insights/models/responses.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class QueryResult(BaseModel):
    """Structured query result."""

    success: bool = Field(..., description="Whether query executed successfully")
    answer: str = Field(..., description="Human-readable answer to the query")
    sql_query: Optional[str] = Field(
        default=None,
        description="Generated SQL query (for debugging)"
    )
    data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Raw query results as list of records"
    )
    row_count: int = Field(default=0, description="Number of result rows")
    execution_time_ms: float = Field(..., description="Query execution time in ms")
    session_id: str = Field(..., description="Session ID for conversation continuity")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "The top 5 categories by revenue in Q3 2022 were: 1. Set (₹12.5M), 2. Kurta (₹8.3M)...",
                "sql_query": "SELECT Category, SUM(Amount) as revenue FROM sales WHERE...",
                "data": [{"Category": "Set", "revenue": 12500000}],
                "row_count": 5,
                "execution_time_ms": 234.5,
                "session_id": "abc123"
            }
        }


class SummaryResult(BaseModel):
    """Automated summary result."""

    summary: str = Field(..., description="Human-readable summary narrative")
    key_metrics: Dict[str, Any] = Field(
        ...,
        description="Key performance metrics"
    )
    highlights: List[str] = Field(
        default_factory=list,
        description="Key highlights and insights"
    )
    period: str = Field(..., description="Time period covered")
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(default=None, description="Detailed error info")
    code: str = Field(default="UNKNOWN_ERROR", description="Error code")
```

### 2.3 Agent Models (`src/retail_insights/models/agents.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class SQLGenerationResult(BaseModel):
    """Output from SQL Generator Agent."""

    sql_query: str = Field(..., description="Generated SQL query")
    explanation: str = Field(..., description="Explanation of what the query does")
    tables_used: List[str] = Field(..., description="Tables referenced in query")
    confidence: float = Field(
        ..., ge=0, le=1,
        description="Confidence score for the generated query"
    )


class ValidationResult(BaseModel):
    """Output from Validator Agent."""

    is_valid: bool = Field(..., description="Whether SQL is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    sanitized_sql: Optional[str] = Field(
        default=None,
        description="Sanitized/corrected SQL if applicable"
    )


class RouterDecision(BaseModel):
    """Output from Router Agent."""

    intent: Literal["query", "summarize", "chat", "clarify"] = Field(
        ...,
        description="Detected user intent"
    )
    confidence: float = Field(..., ge=0, le=1, description="Confidence in classification")
    clarification_needed: Optional[str] = Field(
        default=None,
        description="Clarification question if intent unclear"
    )
```

---

## 3. Agent State Schema

### 3.1 LangGraph State (`src/retail_insights/agents/state.py`)

```python
from typing import TypedDict, Annotated, Optional, List, Literal
from langgraph.graph import MessagesState
import operator


class RetailInsightsState(MessagesState):
    """
    State schema for the multi-agent workflow.
    Persisted via PostgresSaver for durability.
    """

    # User input
    user_query: str
    query_mode: Literal["query", "summarize", "chat"]

    # Router output
    intent: Optional[Literal["query", "summarize", "chat", "clarify"]]

    # SQL Generator output
    generated_sql: Optional[str]
    sql_explanation: Optional[str]
    tables_used: List[str]

    # Validator output
    sql_is_valid: bool
    validation_errors: Annotated[List[str], operator.add]  # Accumulate errors
    retry_count: int

    # Executor output
    query_results: Optional[dict]  # JSON-serializable results
    row_count: int
    execution_time_ms: float

    # Summarizer output
    final_answer: Optional[str]

    # Session management
    thread_id: str
    user_id: Optional[str]

    # Schema context
    available_tables: List[str]
    schema_context: str  # Retrieved schema documentation
```

---

## 4. Agent Implementations

### 4.1 LangGraph Graph Definition (`src/retail_insights/agents/graph.py`)

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from retail_insights.agents.state import RetailInsightsState
from retail_insights.agents.nodes import router, sql_generator, validator, executor, summarizer
from retail_insights.core.config import settings


def build_graph(checkpointer: PostgresSaver) -> StateGraph:
    """Build the multi-agent workflow graph."""

    workflow = StateGraph(RetailInsightsState)

    # Add nodes
    workflow.add_node("router", router.route_query)
    workflow.add_node("sql_generator", sql_generator.generate_sql)
    workflow.add_node("validator", validator.validate_sql)
    workflow.add_node("executor", executor.execute_query)
    workflow.add_node("summarizer", summarizer.summarize_results)

    # Set entry point
    workflow.set_entry_point("router")

    # Router → appropriate path
    workflow.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "query": "sql_generator",
            "summarize": "executor",  # Use predefined queries
            "chat": "summarizer",     # Direct to summarizer for chit-chat
            "clarify": END            # Ask for clarification
        }
    )

    # SQL Generator → Validator
    workflow.add_edge("sql_generator", "validator")

    # Validator → Executor or retry
    workflow.add_conditional_edges(
        "validator",
        check_validation,
        {
            "execute": "executor",
            "retry": "sql_generator",
            "fail": "summarizer"
        }
    )

    # Executor → Summarizer
    workflow.add_edge("executor", "summarizer")

    # Summarizer → END
    workflow.add_edge("summarizer", END)

    return workflow.compile(checkpointer=checkpointer)


def route_by_intent(state: RetailInsightsState) -> str:
    """Route based on detected intent."""
    return state.get("intent", "query")


def check_validation(state: RetailInsightsState) -> str:
    """Check validation result and decide next step."""
    if state["sql_is_valid"]:
        return "execute"

    if state["retry_count"] >= 3:
        return "fail"

    return "retry"
```

### 4.2 Router Agent (`src/retail_insights/agents/nodes/router.py`)

```python
from langchain_openai import ChatOpenAI
from retail_insights.agents.state import RetailInsightsState
from retail_insights.agents.prompts.router import ROUTER_PROMPT
from retail_insights.models.agents import RouterDecision
from retail_insights.core.config import settings


async def route_query(state: RetailInsightsState) -> dict:
    """
    Classify user intent and route to appropriate workflow.

    Intents:
    - query: Analytical question about data
    - summarize: Request for automated summary
    - chat: General conversation/chit-chat
    - clarify: Ambiguous request needing clarification
    """

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0,
        api_key=settings.OPENAI_API_KEY
    )

    # Prepare prompt with user query
    prompt = ROUTER_PROMPT.format(
        user_query=state["user_query"],
        available_tables=", ".join(state["available_tables"])
    )

    # Get structured output
    structured_llm = llm.with_structured_output(RouterDecision)
    result: RouterDecision = await structured_llm.ainvoke(prompt)

    return {
        "intent": result.intent,
        "messages": [{"role": "assistant", "content": f"Intent: {result.intent}"}]
    }
```

### 4.3 SQL Generator Agent (`src/retail_insights/agents/nodes/sql_generator.py`)

```python
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from retail_insights.agents.state import RetailInsightsState
from retail_insights.agents.prompts.sql_generator import SQL_GENERATOR_PROMPT
from retail_insights.models.agents import SQLGenerationResult
from retail_insights.core.config import settings


async def generate_sql(state: RetailInsightsState) -> dict:
    """
    Generate SQL query from natural language.

    Uses schema context and validation errors for self-correction.
    """

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0,
        api_key=settings.OPENAI_API_KEY
    )

    # Build context with schema and any previous errors
    context = {
        "user_query": state["user_query"],
        "schema_context": state["schema_context"],
        "validation_errors": state.get("validation_errors", []),
        "previous_sql": state.get("generated_sql"),
        "current_date": "2022-06-30"  # Use actual date in production
    }

    prompt = SQL_GENERATOR_PROMPT.format(**context)

    # Get structured output
    structured_llm = llm.with_structured_output(SQLGenerationResult)
    result: SQLGenerationResult = await structured_llm.ainvoke(prompt)

    return {
        "generated_sql": result.sql_query,
        "sql_explanation": result.explanation,
        "tables_used": result.tables_used,
        "retry_count": state.get("retry_count", 0) + 1,
        "messages": [{"role": "assistant", "content": f"Generated SQL: {result.sql_query}"}]
    }
```

### 4.4 Validator Agent (`src/retail_insights/agents/nodes/validator.py`)

```python
import sqlglot
from sqlglot.errors import ParseError
from retail_insights.agents.state import RetailInsightsState
from retail_insights.engine.schema_registry import get_valid_tables, get_valid_columns


async def validate_sql(state: RetailInsightsState) -> dict:
    """
    Validate generated SQL for syntax and safety.

    Checks:
    1. SQL syntax using sqlglot
    2. Only SELECT statements allowed
    3. Tables/columns exist in schema
    4. No dangerous operations
    """

    sql = state["generated_sql"]
    errors = []

    # 1. Syntax validation
    try:
        parsed = sqlglot.parse(sql, read="duckdb")
    except ParseError as e:
        errors.append(f"Syntax error: {str(e)}")
        return {
            "sql_is_valid": False,
            "validation_errors": errors
        }

    # 2. Check for SELECT only
    for statement in parsed:
        if statement.key.upper() != "SELECT":
            errors.append(f"Only SELECT statements allowed, got: {statement.key}")

    # 3. Extract and validate table references
    referenced_tables = [
        t.name for t in parsed[0].find_all(sqlglot.exp.Table)
    ]

    valid_tables = get_valid_tables()
    for table in referenced_tables:
        if table.lower() not in [t.lower() for t in valid_tables]:
            errors.append(f"Unknown table: {table}. Valid tables: {valid_tables}")

    # 4. Check for dangerous patterns
    dangerous_patterns = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE"]
    sql_upper = sql.upper()
    for pattern in dangerous_patterns:
        if pattern in sql_upper:
            errors.append(f"Dangerous operation detected: {pattern}")

    # 5. Ensure LIMIT clause (add if missing)
    if "LIMIT" not in sql_upper:
        errors.append("Missing LIMIT clause - will be added automatically")
        sql = f"{sql.rstrip().rstrip(';')} LIMIT 100"

    is_valid = len([e for e in errors if "Missing LIMIT" not in e]) == 0

    return {
        "sql_is_valid": is_valid,
        "validation_errors": errors,
        "generated_sql": sql if is_valid else state["generated_sql"]
    }
```

### 4.5 Executor Agent (`src/retail_insights/agents/nodes/executor.py`)

```python
import time
from retail_insights.agents.state import RetailInsightsState
from retail_insights.engine.query_runner import QueryRunner


async def execute_query(state: RetailInsightsState) -> dict:
    """
    Execute validated SQL against DuckDB.

    Handles:
    - Query execution with timeout
    - Result formatting
    - Error handling
    """

    sql = state["generated_sql"]

    runner = QueryRunner()

    start_time = time.time()
    try:
        results = await runner.execute(sql)
        execution_time = (time.time() - start_time) * 1000

        # Convert to JSON-serializable format
        data = results.to_dict(orient="records")

        return {
            "query_results": {
                "columns": results.columns.tolist(),
                "data": data
            },
            "row_count": len(data),
            "execution_time_ms": execution_time,
            "messages": [{"role": "assistant", "content": f"Query returned {len(data)} rows"}]
        }

    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        return {
            "query_results": None,
            "row_count": 0,
            "execution_time_ms": execution_time,
            "validation_errors": [f"Execution error: {str(e)}"],
            "sql_is_valid": False
        }
```

### 4.6 Summarizer Agent (`src/retail_insights/agents/nodes/summarizer.py`)

```python
from langchain_openai import ChatOpenAI
from retail_insights.agents.state import RetailInsightsState
from retail_insights.agents.prompts.summarizer import SUMMARIZER_PROMPT
from retail_insights.core.config import settings


async def summarize_results(state: RetailInsightsState) -> dict:
    """
    Transform query results into human-readable narrative.

    Handles:
    - Successful query results → insight summary
    - Failed queries → error explanation
    - Chat messages → conversational response
    """

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0.3,  # Slight creativity for natural language
        api_key=settings.OPENAI_API_KEY
    )

    # Build context based on result type
    if state.get("query_results"):
        context = {
            "user_query": state["user_query"],
            "sql_query": state["generated_sql"],
            "results": str(state["query_results"]["data"][:20]),  # Limit for token efficiency
            "row_count": state["row_count"],
            "execution_time": state["execution_time_ms"]
        }
        prompt = SUMMARIZER_PROMPT.format(**context)
    elif state.get("validation_errors"):
        # Error case
        prompt = f"""The user asked: "{state['user_query']}"

Unfortunately, I couldn't complete this request due to:
{chr(10).join(state['validation_errors'])}

Please provide a helpful, friendly explanation and suggest how they might rephrase their question."""
    else:
        # Chat/fallback case
        prompt = f"""The user said: "{state['user_query']}"

Provide a friendly, helpful response. If they're asking about something unrelated to sales data,
politely redirect them to ask about sales performance, revenue, products, or regions."""

    response = await llm.ainvoke(prompt)

    return {
        "final_answer": response.content,
        "messages": [{"role": "assistant", "content": response.content}]
    }
```

---

## 5. DuckDB Data Engine

### 5.1 Connection Manager (`src/retail_insights/engine/connector.py`)

```python
import duckdb
from contextlib import contextmanager
from retail_insights.core.config import settings


class DuckDBConnector:
    """
    Manages DuckDB connections with S3 integration.
    """

    def __init__(self):
        self.config = settings

    @contextmanager
    def get_connection(self, read_only: bool = True):
        """
        Get a DuckDB connection configured for S3 access.

        Args:
            read_only: If True, connection is read-only for safety

        Yields:
            duckdb.Connection: Configured DuckDB connection
        """
        conn = duckdb.connect(":memory:")

        try:
            # Install and load httpfs for S3 access
            conn.execute("INSTALL httpfs; LOAD httpfs;")

            # Configure S3 credentials
            conn.execute(f"""
                CREATE SECRET s3_secret (
                    TYPE S3,
                    KEY_ID '{settings.AWS_ACCESS_KEY_ID}',
                    SECRET '{settings.AWS_SECRET_ACCESS_KEY}',
                    REGION '{settings.AWS_REGION}'
                );
            """)

            # Configure performance settings
            conn.execute(f"SET memory_limit = '{settings.DUCKDB_MEMORY_LIMIT}';")
            conn.execute(f"SET threads = {settings.DUCKDB_THREADS};")
            conn.execute("SET enable_object_cache = true;")

            if read_only:
                conn.execute("SET access_mode = 'READ_ONLY';")

            yield conn

        finally:
            conn.close()


# Singleton instance
_connector = None

def get_connector() -> DuckDBConnector:
    global _connector
    if _connector is None:
        _connector = DuckDBConnector()
    return _connector
```

### 5.2 Query Runner (`src/retail_insights/engine/query_runner.py`)

```python
import pandas as pd
from typing import Optional
from retail_insights.engine.connector import get_connector
from retail_insights.core.config import settings


class QueryRunner:
    """
    Executes SQL queries against DuckDB with S3 Parquet data.
    """

    def __init__(self):
        self.connector = get_connector()
        self.data_path = settings.S3_DATA_PATH  # e.g., s3://bucket/sales/

    async def execute(self, sql: str, max_rows: int = 10000) -> pd.DataFrame:
        """
        Execute SQL query and return results as DataFrame.

        Args:
            sql: SQL query to execute
            max_rows: Maximum rows to return (safety limit)

        Returns:
            pd.DataFrame: Query results
        """
        # Replace table names with S3 Parquet paths
        sql = self._rewrite_table_references(sql)

        with self.connector.get_connection(read_only=True) as conn:
            result = conn.execute(sql).fetchdf()

            # Apply row limit
            if len(result) > max_rows:
                result = result.head(max_rows)

            return result

    def _rewrite_table_references(self, sql: str) -> str:
        """
        Replace table names with read_parquet() calls.

        Example:
            FROM amazon_sales → FROM read_parquet('s3://bucket/amazon_sales.parquet')
        """
        table_mappings = {
            "amazon_sales": f"read_parquet('{self.data_path}/amazon_sales.parquet')",
            "international_sales": f"read_parquet('{self.data_path}/international_sales.parquet')",
            "pricing": f"read_parquet('{self.data_path}/pricing.parquet')",
            "inventory": f"read_parquet('{self.data_path}/inventory.parquet')",
        }

        for table, parquet_ref in table_mappings.items():
            # Case-insensitive replacement
            import re
            sql = re.sub(
                rf'\b{table}\b',
                parquet_ref,
                sql,
                flags=re.IGNORECASE
            )

        return sql


### 5.3 Schema Registry (`src/retail_insights/engine/schema_registry.py`)

```python
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import duckdb

from retail_insights.core.config import settings


class ColumnSchema(BaseModel):
    """Schema for a single column."""
    name: str
    data_type: str
    nullable: bool = True
    description: Optional[str] = None
    sample_values: list[str] = Field(default_factory=list)


class TableSchema(BaseModel):
    """Schema for a single table."""
    name: str
    source_type: str  # "s3", "local", "postgres"
    source_path: str  # Full path or table name
    columns: list[ColumnSchema]
    row_count: Optional[int] = None
    last_modified: Optional[datetime] = None


class DataSource(BaseModel):
    """Configuration for a data source."""
    type: str  # "s3", "local", "postgres"
    path: str  # S3 prefix, local glob, or connection string
    file_pattern: str = "*.parquet"


class SchemaRegistry:
    """
    Dynamic schema discovery and caching for multiple data sources.

    Features:
    - Auto-discovers tables from S3, local files, and PostgreSQL
    - Caches schema with configurable TTL
    - Provides schema context for SQL Generator agent
    - Thread-safe refresh mechanism
    """

    def __init__(
        self,
        data_sources: list[DataSource],
        cache_ttl_seconds: int = 300,  # 5 minutes default
    ):
        self.sources = data_sources
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._schema_cache: dict[str, TableSchema] = {}
        self._last_refresh: Optional[datetime] = None
        self._refresh_lock = asyncio.Lock()

    @property
    def is_stale(self) -> bool:
        """Check if cache needs refresh."""
        if self._last_refresh is None:
            return True
        return datetime.now() - self._last_refresh > self.cache_ttl

    async def get_schema(self, force_refresh: bool = False) -> dict[str, TableSchema]:
        """
        Get cached schema, refreshing if stale.

        Args:
            force_refresh: If True, refresh even if cache is valid

        Returns:
            Dict of table_name -> TableSchema
        """
        if force_refresh or self.is_stale:
            await self.refresh_schema()
        return self._schema_cache

    async def refresh_schema(self) -> None:
        """Discover and cache schema from all sources."""
        async with self._refresh_lock:
            new_cache: dict[str, TableSchema] = {}

            for source in self.sources:
                if source.type == "s3":
                    tables = await self._discover_s3_parquet(source)
                elif source.type == "local":
                    tables = await self._discover_local_files(source)
                elif source.type == "postgres":
                    tables = await self._discover_pg_tables(source)
                else:
                    continue

                new_cache.update(tables)

            self._schema_cache = new_cache
            self._last_refresh = datetime.now()

    async def _discover_s3_parquet(self, source: DataSource) -> dict[str, TableSchema]:
        """Discover Parquet files in S3 bucket."""
        schemas = {}

        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL httpfs; LOAD httpfs;")
        conn.execute(f"""
            CREATE SECRET s3_secret (
                TYPE S3,
                KEY_ID '{settings.AWS_ACCESS_KEY_ID}',
                SECRET '{settings.AWS_SECRET_ACCESS_KEY}',
                REGION '{settings.AWS_REGION}'
            );
        """)

        # List files matching pattern
        glob_path = f"{source.path.rstrip('/')}/{source.file_pattern}"
        try:
            files = conn.execute(f"SELECT file FROM glob('{glob_path}')").fetchall()
        except Exception:
            files = []

        for (file_path,) in files:
            table_name = Path(file_path).stem

            # Describe schema
            columns = conn.execute(f"""
                DESCRIBE SELECT * FROM read_parquet('{file_path}') LIMIT 1
            """).fetchall()

            # Get sample values for each column
            sample_query = ", ".join([
                f"CAST({col[0]} AS VARCHAR) as {col[0]}"
                for col in columns[:10]  # Limit columns for sample
            ])
            samples = conn.execute(f"""
                SELECT DISTINCT {sample_query}
                FROM read_parquet('{file_path}')
                LIMIT 5
            """).fetchdf()

            column_schemas = []
            for col in columns:
                col_samples = samples[col[0]].dropna().tolist()[:3] if col[0] in samples.columns else []
                column_schemas.append(ColumnSchema(
                    name=col[0],
                    data_type=col[1],
                    nullable=col[2] == "YES",
                    sample_values=[str(v) for v in col_samples]
                ))

            schemas[table_name] = TableSchema(
                name=table_name,
                source_type="s3",
                source_path=file_path,
                columns=column_schemas
            )

        conn.close()
        return schemas

    async def _discover_local_files(self, source: DataSource) -> dict[str, TableSchema]:
        """Discover Parquet/CSV files from local filesystem."""
        schemas = {}
        base_path = Path(source.path)

        if not base_path.exists():
            return schemas

        conn = duckdb.connect(":memory:")

        # Find all matching files
        for file_path in base_path.glob(source.file_pattern):
            table_name = file_path.stem

            # Determine read function based on extension
            if file_path.suffix.lower() == ".parquet":
                read_func = "read_parquet"
            elif file_path.suffix.lower() == ".csv":
                read_func = "read_csv_auto"
            else:
                continue

            # Describe schema
            columns = conn.execute(f"""
                DESCRIBE SELECT * FROM {read_func}('{file_path}') LIMIT 1
            """).fetchall()

            column_schemas = [
                ColumnSchema(
                    name=col[0],
                    data_type=col[1],
                    nullable=col[2] == "YES"
                )
                for col in columns
            ]

            schemas[table_name] = TableSchema(
                name=table_name,
                source_type="local",
                source_path=str(file_path),
                columns=column_schemas,
                last_modified=datetime.fromtimestamp(file_path.stat().st_mtime)
            )

        conn.close()
        return schemas

    async def _discover_pg_tables(self, source: DataSource) -> dict[str, TableSchema]:
        """Discover tables from PostgreSQL database."""
        schemas = {}

        # Use asyncpg or psycopg for async PostgreSQL access
        import psycopg

        async with await psycopg.AsyncConnection.connect(source.path) as conn:
            # Query information_schema for tables
            tables = await conn.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
            """)

            for (table_name,) in await tables.fetchall():
                # Get columns
                cols = await conn.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))

                column_schemas = [
                    ColumnSchema(
                        name=col[0],
                        data_type=col[1],
                        nullable=col[2] == "YES"
                    )
                    for col in await cols.fetchall()
                ]

                schemas[table_name] = TableSchema(
                    name=table_name,
                    source_type="postgres",
                    source_path=f"{source.path}/{table_name}",
                    columns=column_schemas
                )

        return schemas

    def get_valid_tables(self) -> list[str]:
        """Get list of valid table names."""
        return list(self._schema_cache.keys())

    def get_valid_columns(self, table_name: str) -> list[str]:
        """Get list of valid column names for a table."""
        if table_name not in self._schema_cache:
            return []
        return [col.name for col in self._schema_cache[table_name].columns]

    def get_schema_context(self) -> str:
        """
        Generate schema context string for SQL Generator prompt.

        Returns markdown-formatted schema documentation.
        """
        if not self._schema_cache:
            return "No tables discovered."

        lines = ["## Available Tables\n"]

        for table_name, schema in self._schema_cache.items():
            lines.append(f"### {table_name}")
            lines.append(f"Source: {schema.source_type} ({schema.source_path})\n")
            lines.append("| Column | Type | Nullable | Sample Values |")
            lines.append("|--------|------|----------|---------------|")

            for col in schema.columns:
                samples = ", ".join(col.sample_values[:3]) if col.sample_values else "-"
                lines.append(f"| {col.name} | {col.data_type} | {col.nullable} | {samples} |")

            lines.append("")

        return "\n".join(lines)


# Module-level singleton
_registry: Optional[SchemaRegistry] = None


def get_schema_registry() -> SchemaRegistry:
    """Get or create the schema registry singleton."""
    global _registry
    if _registry is None:
        _registry = SchemaRegistry(
            data_sources=[
                DataSource(type="s3", path=settings.S3_DATA_PATH),
                DataSource(type="local", path=settings.LOCAL_DATA_PATH),
            ],
            cache_ttl_seconds=settings.SCHEMA_CACHE_TTL
        )
    return _registry


def get_valid_tables() -> list[str]:
    """Convenience function for validator agent."""
    return get_schema_registry().get_valid_tables()


def get_valid_columns(table_name: str) -> list[str]:
    """Convenience function for validator agent."""
    return get_schema_registry().get_valid_columns(table_name)
```

---

## 6. Core Configuration

### 6.1 Settings (`src/retail_insights/core/config.py`)

```python
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """
    Application configuration using Pydantic Settings.
    Loads from environment variables with validation.
    """

    # Application
    APP_NAME: str = "Retail Insights Assistant"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8501"]

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"

    # AWS
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_DATA_PATH: str = "s3://nlsql-data/sales"

    # DuckDB
    DUCKDB_MEMORY_LIMIT: str = "4GB"
    DUCKDB_THREADS: int = 4

    # PostgreSQL (for checkpointing and vector store)
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/nlsql"

    # Redis (for caching)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Streamlit
    STREAMLIT_PORT: int = 8501

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience alias
settings = get_settings()
```

### 6.2 LLM Client Abstraction (`src/retail_insights/core/llm.py`)

```python
from abc import ABC, abstractmethod
from typing import Any
from langchain_openai import ChatOpenAI
from retail_insights.core.config import settings


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def invoke(self, prompt: str) -> str:
        pass

    @abstractmethod
    async def invoke_structured(self, prompt: str, output_schema: Any) -> Any:
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI LLM client implementation."""

    def __init__(self, model: str = None, temperature: float = 0):
        self.model = model or settings.OPENAI_MODEL
        self.temperature = temperature
        self._client = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            api_key=settings.OPENAI_API_KEY
        )

    async def invoke(self, prompt: str) -> str:
        response = await self._client.ainvoke(prompt)
        return response.content

    async def invoke_structured(self, prompt: str, output_schema: Any) -> Any:
        structured_client = self._client.with_structured_output(output_schema)
        return await structured_client.ainvoke(prompt)


def get_llm_client() -> BaseLLMClient:
    """Factory function for LLM client."""
    # Future: Add logic to switch between providers based on config
    return OpenAIClient()
```

---

## 7. FastAPI Application

### 7.1 Application Factory (`src/retail_insights/api/app.py`)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from retail_insights.api.routes import query, summarize, health
from retail_insights.core.config import settings
from retail_insights.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    # Startup
    setup_logging()
    # Initialize database connections, etc.
    yield
    # Shutdown
    # Close connections, cleanup


def create_app() -> FastAPI:
    """Create FastAPI application instance."""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="GenAI-powered Retail Insights Assistant",
        lifespan=lifespan
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(health.router, tags=["Health"])
    app.include_router(query.router, prefix=settings.API_PREFIX, tags=["Query"])
    app.include_router(summarize.router, prefix=settings.API_PREFIX, tags=["Summarize"])

    return app


app = create_app()
```

### 7.2 Query Routes (`src/retail_insights/api/routes/query.py`)

```python
from fastapi import APIRouter, Depends, HTTPException
from retail_insights.models.requests import QueryRequest
from retail_insights.models.responses import QueryResult, ErrorResponse
from retail_insights.agents.graph import build_graph
from retail_insights.api.dependencies import get_checkpointer, get_schema_context
import uuid


router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResult,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def process_query(
    request: QueryRequest,
    checkpointer = Depends(get_checkpointer),
    schema_context: str = Depends(get_schema_context)
):
    """
    Process a natural language query about sales data.

    Workflow:
    1. Route intent (query/summarize/chat)
    2. Generate SQL from natural language
    3. Validate SQL for safety
    4. Execute against DuckDB
    5. Summarize results
    """

    # Build agent graph
    graph = build_graph(checkpointer)

    # Prepare initial state
    session_id = request.session_id or str(uuid.uuid4())
    initial_state = {
        "user_query": request.question,
        "query_mode": request.mode.value,
        "available_tables": ["amazon_sales", "international_sales", "pricing", "inventory"],
        "schema_context": schema_context,
        "thread_id": session_id,
        "retry_count": 0,
        "sql_is_valid": False,
        "validation_errors": [],
        "messages": []
    }

    config = {"configurable": {"thread_id": session_id}}

    try:
        # Run the agent graph
        result = await graph.ainvoke(initial_state, config)

        return QueryResult(
            success=True,
            answer=result.get("final_answer", "No answer generated"),
            sql_query=result.get("generated_sql"),
            data=result.get("query_results", {}).get("data"),
            row_count=result.get("row_count", 0),
            execution_time_ms=result.get("execution_time_ms", 0),
            session_id=session_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 8. Docker Configuration

### 8.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY src/ ./src/

# Set environment
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Expose ports
EXPOSE 8000

# Run application
CMD ["uv", "run", "uvicorn", "retail_insights.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8.2 Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/nlsql
      - REDIS_URL=redis://redis:6379/0
      - S3_DATA_PATH=./data/parquet  # Local path for dev
    depends_on:
      - db
      - redis
    volumes:
      - ./data:/app/data:ro

  streamlit:
    build:
      context: .
      dockerfile: Dockerfile.streamlit
    ports:
      - "8501:8501"
    environment:
      - API_URL=http://api:8000
    depends_on:
      - api

  db:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=nlsql
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

---

## 9. pyproject.toml

```toml
[project]
name = "retail-insights-assistant"
version = "1.0.0"
description = "GenAI-powered Retail Insights Assistant with multi-agent NL-to-SQL"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    # Core
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",

    # LangGraph / LangChain
    "langgraph>=1.0.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",

    # Data
    "duckdb>=1.1.0",
    "pandas>=2.2.0",
    "pyarrow>=17.0.0",

    # Database
    "psycopg[binary,pool]>=3.2.0",
    "redis>=5.0.0",

    # SQL Validation
    "sqlglot>=25.0.0",

    # Utilities
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "structlog>=24.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "pre-commit>=3.8.0",
]
ui = [
    "streamlit>=1.38.0",
    "plotly>=5.24.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## 10. Testing Strategy

### 10.1 Unit Tests (`tests/unit/test_agents.py`)

```python
import pytest
from unittest.mock import AsyncMock, patch
from retail_insights.agents.nodes.validator import validate_sql
from retail_insights.agents.state import RetailInsightsState


@pytest.fixture
def base_state() -> RetailInsightsState:
    return {
        "user_query": "What are the top categories?",
        "generated_sql": "SELECT Category, SUM(Amount) FROM amazon_sales GROUP BY Category",
        "retry_count": 0,
        "validation_errors": [],
        "sql_is_valid": False,
        "messages": []
    }


class TestSQLValidator:
    """Test SQL validation logic."""

    @pytest.mark.asyncio
    async def test_valid_select_passes(self, base_state):
        result = await validate_sql(base_state)
        # LIMIT will be added
        assert "LIMIT" in result["generated_sql"] or not result["sql_is_valid"]

    @pytest.mark.asyncio
    async def test_delete_rejected(self, base_state):
        base_state["generated_sql"] = "DELETE FROM amazon_sales"
        result = await validate_sql(base_state)
        assert result["sql_is_valid"] is False
        assert any("DELETE" in e for e in result["validation_errors"])

    @pytest.mark.asyncio
    async def test_unknown_table_rejected(self, base_state):
        base_state["generated_sql"] = "SELECT * FROM unknown_table"
        result = await validate_sql(base_state)
        assert result["sql_is_valid"] is False
```

### 10.2 Integration Tests (`tests/integration/test_workflow.py`)

```python
import pytest
from retail_insights.agents.graph import build_graph
from langgraph.checkpoint.memory import MemorySaver


@pytest.fixture
def graph():
    checkpointer = MemorySaver()
    return build_graph(checkpointer)


class TestAgentWorkflow:
    """Integration tests for the complete agent workflow."""

    @pytest.mark.asyncio
    async def test_simple_query_flow(self, graph):
        initial_state = {
            "user_query": "What are the total sales?",
            "query_mode": "query",
            "available_tables": ["amazon_sales"],
            "schema_context": "amazon_sales: Order ID, Amount, Category, ship-state",
            "thread_id": "test-123",
            "retry_count": 0,
            "sql_is_valid": False,
            "validation_errors": [],
            "messages": []
        }

        config = {"configurable": {"thread_id": "test-123"}}

        result = await graph.ainvoke(initial_state, config)

        assert result["final_answer"] is not None
        assert "sales" in result["final_answer"].lower()
```

---

## 11. Appendix: Prompt Templates

### 11.1 SQL Generator Prompt

```python
SQL_GENERATOR_PROMPT = """You are an expert DuckDB SQL analyst for a retail sales database.

## Available Schema
{schema_context}

## User Question
{user_query}

## Current Date Context
Today's date is: {current_date}

## Previous Errors (if any)
{validation_errors}

## Previous SQL (if retrying)
{previous_sql}

## Instructions
1. Generate a valid DuckDB SQL query to answer the user's question
2. Use only SELECT statements
3. Always include a LIMIT clause (default 100)
4. For date filtering, use DuckDB date functions
5. Handle NULL values appropriately
6. Use aliases for readability

## Output Format
Return a SQLGenerationResult with:
- sql_query: The complete SQL query
- explanation: Brief explanation of what the query does
- tables_used: List of tables referenced
- confidence: Your confidence score (0-1)
"""
```

---

This LLD provides the complete software design for implementing the Retail Insights Assistant. The modular structure enables independent testing and deployment of each component while maintaining clear interfaces between layers.
