"""LangGraph graph builder for the Retail Insights multi-agent workflow.

This module defines the workflow graph connecting Router, SQL Generator,
Validator, Executor, and Summarizer agents with conditional routing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from retail_insights.agents.nodes.router import route_query
from retail_insights.agents.state import RetailInsightsState

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph


# Constants
MAX_RETRIES = 3


def route_by_intent(state: RetailInsightsState) -> str:
    """Route based on detected intent from the Router agent.

    Args:
        state: Current workflow state with intent field set.

    Returns:
        Next node name based on intent:
        - "sql_generator" for query intent
        - "executor" for summarize intent (uses predefined queries)
        - "summarizer" for chat intent (direct conversation)
        - "__end__" for clarify intent (return to user)
    """
    intent = state.get("intent", "query")

    routing_map = {
        "query": "sql_generator",
        "summarize": "executor",
        "chat": "summarizer",
        "clarify": END,
    }

    return routing_map.get(intent, "sql_generator")


def check_validation(state: RetailInsightsState) -> str:
    """Check SQL validation result and decide next step.

    Implements retry logic: if validation fails and retries remain,
    route back to SQL generator. Otherwise, execute or fail.

    Args:
        state: Current workflow state with validation results.

    Returns:
        Next node name:
        - "executor" if SQL is valid
        - "sql_generator" if invalid but retries remain
        - "summarizer" if max retries exceeded (fail gracefully)
    """
    if state.get("sql_is_valid", False):
        return "executor"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", MAX_RETRIES)

    if retry_count >= max_retries:
        return "summarizer"  # Fail gracefully with error message

    return "sql_generator"


# Placeholder node functions (will be replaced by actual agent implementations)
async def placeholder_router_node(state: RetailInsightsState) -> dict:
    """Placeholder for Router agent - classifies user intent.

    Used for testing when LLM is not available.
    Real implementation: route_query from retail_insights.agents.nodes.router
    """
    return {
        "intent": "query",
        "intent_confidence": 1.0,
    }


async def sql_generator_node(state: RetailInsightsState) -> dict:
    """Placeholder for SQL Generator agent - generates SQL from NL query.

    TODO: Implement in TICKET-010 with LLM-based SQL generation.
    """
    placeholder_sql = "SELECT * FROM sales LIMIT 10"  # nosec B608 - static placeholder query
    return {
        "generated_sql": placeholder_sql,
        "sql_explanation": f"Placeholder SQL query for: {state['user_query']}",
        "tables_used": ["sales"],
        "retry_count": state.get("retry_count", 0) + 1,
    }


async def validator_node(state: RetailInsightsState) -> dict:
    """Placeholder for Validator agent - validates SQL syntax and safety.

    TODO: Implement in TICKET-011 with sqlglot validation.
    """
    return {
        "sql_is_valid": True,
        "validation_status": "valid",
    }


async def executor_node(state: RetailInsightsState) -> dict:
    """Placeholder for Executor agent - executes SQL against DuckDB.

    TODO: Implement in TICKET-012 with DuckDB execution.
    """
    return {
        "query_results": [{"placeholder": "result"}],
        "row_count": 1,
        "execution_time_ms": 0.0,
    }


async def summarizer_node(state: RetailInsightsState) -> dict:
    """Placeholder for Summarizer agent - generates human-readable response.

    TODO: Implement in TICKET-013 with LLM-based summarization.
    """
    results = state.get("query_results")
    error = state.get("execution_error")
    validation_errors = state.get("validation_errors", [])

    if validation_errors and state.get("validation_status") == "failed":
        return {
            "final_answer": f"I couldn't generate a valid SQL query. Errors: {validation_errors}",
        }

    if error:
        return {
            "final_answer": f"Query execution failed: {error}",
        }

    if results:
        return {
            "final_answer": f"Query returned {state.get('row_count', 0)} rows.",
        }

    # Chat intent fallback
    return {
        "final_answer": "I'm your retail insights assistant. How can I help you today?",
    }


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    *,
    use_placeholder_router: bool = False,
) -> CompiledStateGraph:
    """Build the multi-agent workflow graph.

    Creates a StateGraph with the following flow:
    1. Router: Classify intent (query/summarize/chat/clarify)
    2. SQL Generator: Generate SQL from natural language (if query intent)
    3. Validator: Check SQL syntax and safety
    4. Executor: Run SQL against DuckDB
    5. Summarizer: Generate human-readable response

    Retry logic: Validator can route back to SQL Generator up to MAX_RETRIES times.

    Args:
        checkpointer: Optional checkpoint saver for persistence (PostgresSaver/MemorySaver).
        use_placeholder_router: If True, use placeholder router for testing (no LLM calls).
            Defaults to False (uses real LLM-based router).

    Returns:
        Compiled StateGraph ready for invocation.

    Example:
        >>> from langgraph.checkpoint.memory import MemorySaver
        >>> graph = build_graph(MemorySaver())
        >>> result = await graph.ainvoke(
        ...     create_initial_state("What are the top 5 products?", "thread-1"),
        ...     config={"configurable": {"thread_id": "thread-1"}}
        ... )
    """
    workflow = StateGraph(RetailInsightsState)

    # Select router node (real or placeholder)
    router_node = placeholder_router_node if use_placeholder_router else route_query

    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("sql_generator", sql_generator_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("summarizer", summarizer_node)

    # Set entry point
    workflow.set_entry_point("router")

    # Router → conditional routing based on intent
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

    # SQL Generator → Validator
    workflow.add_edge("sql_generator", "validator")

    # Validator → conditional routing based on validation result
    workflow.add_conditional_edges(
        "validator",
        check_validation,
        {
            "executor": "executor",
            "sql_generator": "sql_generator",  # Retry loop
            "summarizer": "summarizer",  # Max retries exceeded
        },
    )

    # Executor → Summarizer
    workflow.add_edge("executor", "summarizer")

    # Summarizer → END
    workflow.add_edge("summarizer", END)

    # Compile with optional checkpointer
    return workflow.compile(checkpointer=checkpointer)


def get_memory_checkpointer():
    """Get an in-memory checkpointer for testing.

    Returns:
        MemorySaver instance for non-persistent state storage.
    """
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


async def get_postgres_checkpointer(connection_string: str):
    """Get a PostgreSQL checkpointer for production.

    Args:
        connection_string: PostgreSQL connection string.

    Returns:
        AsyncPostgresSaver instance for persistent state storage.

    Note:
        Requires psycopg pool to be configured. Call .setup() before first use.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(conninfo=connection_string)
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    return checkpointer
