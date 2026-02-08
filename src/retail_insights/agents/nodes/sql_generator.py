"""SQL Generator agent node for natural language to SQL translation.

This module implements the SQL Generator agent that translates
user questions into DuckDB SQL queries with schema awareness
and self-correction support for retry loops.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from retail_insights.agents.prompts.sql_generator import format_sql_generator_prompt
from retail_insights.agents.state import RetailInsightsState
from retail_insights.core.config import get_settings
from retail_insights.models.agents import SQLGenerationResult

logger = structlog.get_logger(__name__)


async def generate_sql(state: RetailInsightsState) -> dict:
    """Generate SQL query from natural language question.

    Uses schema context for accurate table/column references and
    validation errors from previous attempts for self-correction.

    Args:
        state: Current workflow state containing user_query, schema_context,
            and optionally validation_errors and previous generated_sql.

    Returns:
        Dict with updates to state:
        - generated_sql: The SQL query string
        - sql_explanation: Natural language explanation
        - tables_used: List of tables referenced
        - retry_count: Incremented retry counter

    Example:
        >>> state = create_initial_state("What are total sales?", "thread-1")
        >>> state["schema_context"] = "Table: amazon_sales (Amount, Category, Date)"
        >>> result = await generate_sql(state)
        >>> result["generated_sql"]
        'SELECT SUM(Amount) as total_revenue FROM amazon_sales LIMIT 1'
    """
    settings = get_settings()

    retry_count = state.get("retry_count", 0)
    is_retry = retry_count > 0

    logger.info(
        "generating_sql",
        user_query=state["user_query"],
        thread_id=state["thread_id"],
        retry_count=retry_count,
        is_retry=is_retry,
    )

    # Initialize LLM with structured output
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,  # Deterministic for SQL generation
        api_key=settings.openai_api_key.get_secret_value(),
    )
    structured_llm = llm.with_structured_output(SQLGenerationResult)

    # Get current date for temporal context
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Format prompts with schema and retry context
    system_prompt, user_prompt = format_sql_generator_prompt(
        user_query=state["user_query"],
        schema_context=state.get("schema_context", ""),
        validation_errors=state.get("validation_errors") if is_retry else None,
        previous_sql=state.get("generated_sql") if is_retry else None,
        current_date=current_date,
    )

    # Invoke LLM for SQL generation
    try:
        result: SQLGenerationResult = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )

        logger.info(
            "sql_generated",
            sql_query=result.sql_query[:200],  # Truncate for logging
            tables_used=result.tables_used,
            columns_used=result.columns_used,
            retry_count=retry_count + 1,
        )

        return {
            "generated_sql": result.sql_query,
            "sql_explanation": result.explanation,
            "tables_used": result.tables_used,
            "retry_count": retry_count + 1,
        }

    except Exception as e:
        logger.error("sql_generation_error", error=str(e), retry_count=retry_count)
        # Return a failed state that will trigger retry or summarizer error handling
        return {
            "generated_sql": None,
            "sql_explanation": f"Failed to generate SQL: {e!s}",
            "tables_used": [],
            "retry_count": retry_count + 1,
            "validation_errors": [f"SQL Generation failed: {e!s}"],
            "sql_is_valid": False,
            "validation_status": "failed",
        }


def create_mock_sql_generator(
    sql_query: str = "SELECT * FROM amazon_sales LIMIT 10",
    explanation: str = "Mock SQL query for testing",
    tables_used: list[str] | None = None,
    columns_used: list[str] | None = None,
    *,
    should_fail: bool = False,
    failure_message: str = "Mock failure",
):
    """Create a mock SQL generator function for testing.

    Args:
        sql_query: The SQL query to return.
        explanation: Explanation to return.
        tables_used: Tables to report as used.
        columns_used: Columns to report as used.
        should_fail: If True, simulate a generation failure.
        failure_message: Error message when failing.

    Returns:
        Async function matching generate_sql signature.
    """

    async def mock_generate_sql(state: RetailInsightsState) -> dict:
        retry_count = state.get("retry_count", 0)

        if should_fail:
            return {
                "generated_sql": None,
                "sql_explanation": failure_message,
                "tables_used": [],
                "retry_count": retry_count + 1,
                "validation_errors": [failure_message],
                "sql_is_valid": False,
                "validation_status": "failed",
            }

        return {
            "generated_sql": sql_query,
            "sql_explanation": explanation,
            "tables_used": tables_used or ["amazon_sales"],
            "retry_count": retry_count + 1,
        }

    return mock_generate_sql
