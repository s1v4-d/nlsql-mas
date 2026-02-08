"""E2E test fixtures.

This module provides fixtures for end-to-end testing of the Retail Insights
multi-agent workflow, including sample data, DuckDB setup, and mock LLM responses.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from tests.fixtures.data.sample_data import generate_edge_case_data, generate_sample_data

if TYPE_CHECKING:
    from retail_insights.agents.state import RetailInsightsState


@pytest.fixture(autouse=True)
def mock_env():
    """Set required environment variables for E2E tests."""
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-e2e-api-key",
            "DEBUG": "true",
            "ENVIRONMENT": "development",
            "RATE_LIMIT_ENABLED": "false",
        },
    ):
        from retail_insights.api.rate_limit import reset_limiter
        from retail_insights.core.config import get_settings

        reset_limiter()
        get_settings.cache_clear()
        yield
        reset_limiter()
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def sample_data_path(tmp_path_factory) -> Path:
    """Generate sample CSV data for E2E tests (session-scoped for reuse)."""
    data_dir = tmp_path_factory.mktemp("e2e_data")
    generate_sample_data(data_dir, num_rows=100, seed=42)
    return data_dir


@pytest.fixture(scope="session")
def edge_case_data_path(tmp_path_factory) -> Path:
    """Generate edge case CSV data for E2E tests."""
    data_dir = tmp_path_factory.mktemp("edge_case_data")
    generate_edge_case_data(data_dir)
    return data_dir


@pytest.fixture
def duckdb_connection(sample_data_path: Path):
    """Create a DuckDB connection with sample sales data registered."""
    conn = duckdb.connect(":memory:")

    # Register the sample CSV as a table
    csv_path = sample_data_path / "sample_sales.csv"
    conn.execute(f"""
        CREATE TABLE amazon_sales AS
        SELECT * FROM read_csv_auto('{csv_path}')
    """)

    yield conn
    conn.close()


@pytest.fixture
def duckdb_with_edge_cases(edge_case_data_path: Path):
    """Create a DuckDB connection with edge case data."""
    conn = duckdb.connect(":memory:")

    csv_path = edge_case_data_path / "edge_cases.csv"
    conn.execute(f"""
        CREATE TABLE amazon_sales AS
        SELECT * FROM read_csv_auto('{csv_path}')
    """)

    yield conn
    conn.close()


ROUTER_RESPONSE_MAP = {
    # Query intent patterns
    "top": {"intent": "query", "intent_confidence": 0.95},
    "sales": {"intent": "query", "intent_confidence": 0.92},
    "revenue": {"intent": "query", "intent_confidence": 0.94},
    "count": {"intent": "query", "intent_confidence": 0.90},
    "how many": {"intent": "query", "intent_confidence": 0.93},
    "what": {"intent": "query", "intent_confidence": 0.88},
    "show": {"intent": "query", "intent_confidence": 0.91},
    "list": {"intent": "query", "intent_confidence": 0.89},
    "average": {"intent": "query", "intent_confidence": 0.92},
    "total": {"intent": "query", "intent_confidence": 0.93},
    # Summarize intent patterns
    "summarize": {"intent": "summarize", "intent_confidence": 0.96},
    "overview": {"intent": "summarize", "intent_confidence": 0.90},
    "summary": {"intent": "summarize", "intent_confidence": 0.94},
    # Chat intent patterns
    "hello": {"intent": "chat", "intent_confidence": 0.98},
    "hi": {"intent": "chat", "intent_confidence": 0.97},
    "help": {"intent": "chat", "intent_confidence": 0.92},
    "what can you": {"intent": "chat", "intent_confidence": 0.91},
    "thank": {"intent": "chat", "intent_confidence": 0.95},
}


SQL_GENERATION_MAP = {
    "top 5 categories": """
        SELECT Category, SUM(Amount) as revenue
        FROM amazon_sales
        GROUP BY Category
        ORDER BY revenue DESC
        LIMIT 5
    """,
    "top categories": """
        SELECT Category, SUM(Amount) as revenue
        FROM amazon_sales
        GROUP BY Category
        ORDER BY revenue DESC
        LIMIT 10
    """,
    "sales by state": """
        SELECT "ship-state" as state, SUM(Amount) as revenue, COUNT(*) as order_count
        FROM amazon_sales
        GROUP BY "ship-state"
        ORDER BY revenue DESC
    """,
    "total revenue": """
        SELECT SUM(Amount) as total_revenue
        FROM amazon_sales
    """,
    "average order": """
        SELECT AVG(Amount) as average_order_value
        FROM amazon_sales
    """,
    "count orders": """
        SELECT COUNT(*) as order_count
        FROM amazon_sales
    """,
    "by category": """
        SELECT Category, SUM(Amount) as revenue, COUNT(*) as orders
        FROM amazon_sales
        GROUP BY Category
        ORDER BY revenue DESC
    """,
    "cancelled": """
        SELECT COUNT(*) as cancelled_orders, SUM(Amount) as lost_revenue
        FROM amazon_sales
        WHERE Status = 'Cancelled'
    """,
    "maharashtra": """
        SELECT Category, SUM(Amount) as revenue
        FROM amazon_sales
        WHERE "ship-state" = 'MAHARASHTRA'
        GROUP BY Category
        ORDER BY revenue DESC
    """,
}


@pytest.fixture
def mock_router():
    """Create a mock router that returns deterministic responses."""

    async def _mock_router(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("user_query", "").lower()

        for pattern, response in ROUTER_RESPONSE_MAP.items():
            if pattern in query:
                return {
                    "intent": response["intent"],
                    "intent_confidence": response["intent_confidence"],
                    "clarification_question": None,
                }

        # Default to query intent
        return {
            "intent": "query",
            "intent_confidence": 0.8,
            "clarification_question": None,
        }

    return _mock_router


@pytest.fixture
def mock_sql_generator():
    """Create a mock SQL generator that returns deterministic SQL."""

    async def _mock_sql_generator(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("user_query", "").lower()
        retry_count = state.get("retry_count", 0)

        for pattern, sql in SQL_GENERATION_MAP.items():
            if pattern in query:
                return {
                    "generated_sql": sql.strip(),
                    "sql_explanation": f"Query to analyze: {pattern}",
                    "tables_used": ["amazon_sales"],
                    "retry_count": retry_count + 1,
                }

        # Default fallback query
        return {
            "generated_sql": "SELECT * FROM amazon_sales LIMIT 10",
            "sql_explanation": "Default query showing sample data",
            "tables_used": ["amazon_sales"],
            "retry_count": retry_count + 1,
        }

    return _mock_sql_generator


@pytest.fixture
def mock_summarizer():
    """Create a mock summarizer that generates human-readable responses."""

    async def _mock_summarizer(state: dict[str, Any]) -> dict[str, Any]:
        results = state.get("query_results")
        row_count = state.get("row_count", 0)
        error = state.get("execution_error")
        validation_errors = state.get("validation_errors", [])
        intent = state.get("intent", "query")

        # Handle errors
        if validation_errors and state.get("validation_status") == "failed":
            return {
                "final_answer": f"I couldn't generate a valid SQL query. Errors: {'; '.join(validation_errors)}"
            }

        if error:
            return {"final_answer": f"Query execution failed: {error}"}

        # Handle chat intent
        if intent == "chat":
            return {
                "final_answer": "I'm your retail insights assistant. I can help you analyze sales data, "
                "find top categories, track revenue by region, and answer questions about your retail performance."
            }

        # Handle summarize intent
        if intent == "summarize":
            return {
                "final_answer": "Based on the data, I can see sales across multiple categories including Set, "
                "kurta, and Western Dress. Revenue is distributed across multiple states with varied performance."
            }

        # Handle query results
        if results and row_count > 0:
            if row_count == 1 and len(results[0]) == 1:
                # Single value result (like total, count, avg)
                key, value = list(results[0].items())[0]
                return {
                    "final_answer": f"The {key} is {value:,.2f}"
                    if isinstance(value, float)
                    else f"The {key} is {value}"
                }

            # Multiple rows
            return {
                "final_answer": f"Query returned {row_count} results. The data shows the requested breakdown."
            }

        return {"final_answer": "No results found matching your query."}

    return _mock_summarizer


@pytest.fixture
def deterministic_graph(mock_router, mock_sql_generator, mock_summarizer, duckdb_connection):
    """Create a graph with mocked LLM nodes but real validator/executor."""
    from langgraph.graph import END, StateGraph

    from retail_insights.agents.nodes.executor import execute_query
    from retail_insights.agents.nodes.validator import validate_sql
    from retail_insights.agents.state import RetailInsightsState

    # Patch DuckDB connection for executor
    with patch("retail_insights.engine.connector.DuckDBConnector") as mock_connector_cls:
        mock_connector = MagicMock()
        mock_connector.execute.side_effect = lambda sql: duckdb_connection.execute(sql).fetchdf()
        mock_connector_cls.return_value = mock_connector
        mock_connector_cls.get_instance.return_value = mock_connector

        workflow = StateGraph(RetailInsightsState)

        # Add nodes (mocked LLMs, real validator)
        workflow.add_node("router", mock_router)
        workflow.add_node("sql_generator", mock_sql_generator)
        workflow.add_node("validator", validate_sql)
        workflow.add_node("executor", execute_query)
        workflow.add_node("summarizer", mock_summarizer)

        # Set routing
        workflow.set_entry_point("router")

        def route_by_intent(state):
            intent = state.get("intent", "query")
            routing_map = {
                "query": "sql_generator",
                "summarize": "executor",
                "chat": "summarizer",
                "clarify": END,
            }
            return routing_map.get(intent, "sql_generator")

        def check_validation(state):
            if state.get("sql_is_valid", False):
                return "executor"
            retry_count = state.get("retry_count", 0)
            if retry_count >= state.get("max_retries", 3):
                return "summarizer"
            return "sql_generator"

        workflow.add_conditional_edges(
            "router",
            route_by_intent,
            {
                "sql_generator": "sql_generator",
                "executor": "executor",
                "summarizer": "summarizer",
                END: END,
            },
        )
        workflow.add_edge("sql_generator", "validator")
        workflow.add_conditional_edges(
            "validator",
            check_validation,
            {"executor": "executor", "sql_generator": "sql_generator", "summarizer": "summarizer"},
        )
        workflow.add_edge("executor", "summarizer")
        workflow.add_edge("summarizer", END)

        yield workflow.compile(checkpointer=MemorySaver())


@pytest.fixture
def mock_graph_simple():
    """Create a simple mock graph for basic API testing."""
    graph = MagicMock()

    async def mock_ainvoke(state, config=None):
        return {
            "intent": "query",
            "intent_confidence": 0.95,
            "generated_sql": "SELECT Category, SUM(Amount) as revenue FROM amazon_sales GROUP BY Category LIMIT 5",
            "sql_is_valid": True,
            "validation_status": "valid",
            "query_results": [
                {"Category": "Set", "revenue": 150000.0},
                {"Category": "kurta", "revenue": 80000.0},
                {"Category": "Western Dress", "revenue": 95000.0},
            ],
            "row_count": 3,
            "execution_time_ms": 45.2,
            "final_answer": "The top 3 categories by revenue are: Set ($150,000), Western Dress ($95,000), and kurta ($80,000).",
        }

    graph.ainvoke = AsyncMock(side_effect=mock_ainvoke)

    async def mock_astream(state, config=None, stream_mode=None):
        yield {"router": {"intent": "query", "intent_confidence": 0.95}}
        yield {"sql_generator": {"generated_sql": "SELECT * FROM amazon_sales LIMIT 5"}}
        yield {"validator": {"sql_is_valid": True, "validation_status": "valid"}}
        yield {"executor": {"row_count": 3, "query_results": [{"Category": "Set"}]}}
        yield {"summarizer": {"final_answer": "Query returned 3 results."}}

    graph.astream = MagicMock(return_value=mock_astream(None))

    mock_state = MagicMock()
    mock_state.values = {
        "final_answer": "Query returned 3 results.",
        "generated_sql": "SELECT * FROM amazon_sales LIMIT 5",
        "query_results": [{"Category": "Set"}],
        "row_count": 3,
    }
    graph.aget_state = AsyncMock(return_value=mock_state)

    return graph


@pytest.fixture
def mock_schema_registry():
    """Create a mock schema registry for E2E tests."""
    from retail_insights.engine.schema_registry import SchemaRegistry

    SchemaRegistry.reset_instance()

    registry = MagicMock()
    registry.get_schema_for_prompt.return_value = """
Table: amazon_sales
Columns:
  - Order ID (VARCHAR): Unique order identifier
  - Date (DATE): Order date
  - Status (VARCHAR): Order status (Shipped/Delivered/Cancelled/Returned)
  - Fulfilment (VARCHAR): Fulfilment type (Amazon/Merchant)
  - Category (VARCHAR): Product category
  - Size (VARCHAR): Product size
  - Qty (INTEGER): Quantity ordered
  - Amount (DOUBLE): Order amount in INR
  - ship-city (VARCHAR): Shipping city
  - ship-state (VARCHAR): Shipping state
  - B2B (BOOLEAN): Business-to-business flag
    """
    registry.get_table_info.return_value = {
        "amazon_sales": {
            "columns": [
                "Order ID",
                "Date",
                "Status",
                "Fulfilment",
                "Category",
                "Size",
                "Qty",
                "Amount",
                "ship-city",
                "ship-state",
                "B2B",
            ]
        }
    }
    registry.get_table_names.return_value = ["amazon_sales"]

    yield registry
    SchemaRegistry.reset_instance()


@pytest.fixture
def e2e_app(mock_graph_simple, mock_schema_registry):
    """Create a FastAPI app configured for E2E testing."""
    from retail_insights.core.config import get_settings

    settings = get_settings()

    test_app = FastAPI(title="E2E Test App")

    from retail_insights.api.routes.admin import router as admin_router
    from retail_insights.api.routes.query import router as query_router

    test_app.include_router(admin_router)
    test_app.include_router(query_router)

    test_app.state.settings = settings
    test_app.state.graph = mock_graph_simple
    test_app.state.schema_registry = mock_schema_registry
    test_app.state.checkpointer = MemorySaver()

    @test_app.get("/health")
    async def health():
        return {"status": "healthy"}

    @test_app.get("/ready")
    async def ready():
        return {"status": "ready"}

    return test_app


@pytest.fixture
def e2e_client(e2e_app: FastAPI) -> TestClient:
    """Create a test client for E2E tests."""
    return TestClient(e2e_app)


@pytest.fixture
def create_state():
    """Factory fixture for creating initial workflow states."""
    from retail_insights.agents.state import create_initial_state

    def _create_state(
        query: str,
        thread_id: str = "e2e-test",
        **kwargs,
    ) -> RetailInsightsState:
        return create_initial_state(
            user_query=query,
            thread_id=thread_id,
            available_tables=["amazon_sales"],
            **kwargs,
        )

    return _create_state


QUERY_SCENARIOS = [
    pytest.param(
        "What are the top 5 categories by revenue?",
        {
            "expected_intent": "query",
            "expected_sql_contains": ["Category", "SUM", "GROUP BY", "LIMIT"],
        },
        id="top_categories",
    ),
    pytest.param(
        "Show me sales by state",
        {"expected_intent": "query", "expected_sql_contains": ["ship-state", "SUM"]},
        id="sales_by_state",
    ),
    pytest.param(
        "What is the total revenue?",
        {"expected_intent": "query", "expected_sql_contains": ["SUM", "Amount"]},
        id="total_revenue",
    ),
    pytest.param(
        "How many orders are there?",
        {"expected_intent": "query", "expected_sql_contains": ["COUNT"]},
        id="order_count",
    ),
    pytest.param(
        "Hello, what can you help me with?",
        {"expected_intent": "chat", "expected_sql_contains": None},
        id="chat_greeting",
    ),
    pytest.param(
        "Give me a summary of the data",
        {"expected_intent": "summarize", "expected_sql_contains": None},
        id="summarize_data",
    ),
]


ERROR_SCENARIOS = [
    pytest.param(
        "invalid_sql_syntax",
        "SELEC * FORM amazon_sales",  # Typos
        {"expected_valid": False, "expected_error_contains": "syntax"},
        id="syntax_error",
    ),
    pytest.param(
        "dangerous_sql",
        "DROP TABLE amazon_sales; SELECT * FROM amazon_sales",
        {"expected_valid": False, "expected_error_contains": "DROP"},
        id="sql_injection",
    ),
    pytest.param(
        "unknown_table",
        "SELECT * FROM nonexistent_table",
        {"expected_valid": False, "expected_error_contains": "table"},
        id="unknown_table",
    ),
]
