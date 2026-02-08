"""Summarizer agent node for transforming results into narratives.

This module implements the Summarizer agent that converts SQL query results,
errors, and empty responses into user-friendly natural language summaries.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from retail_insights.agents.prompts.summarizer import format_summarizer_prompt
from retail_insights.agents.state import RetailInsightsState
from retail_insights.core.config import get_settings

logger = structlog.get_logger(__name__)


async def summarize_results(state: RetailInsightsState) -> dict:
    """Transform query results into a human-readable narrative.

    Handles four result scenarios:
    - data: Successful query with results to summarize
    - empty: Query succeeded but returned no rows
    - error: Query execution failed
    - chat: Non-query intent requiring conversational response

    Args:
        state: Current workflow state containing query results or errors.

    Returns:
        Dict with updates to state:
        - final_answer: Human-readable summary for the user
        - messages: List containing the AI response message

    Example:
        >>> state = {..., "query_results": [{"total": 123456}], "row_count": 1}
        >>> result = await summarize_results(state)
        >>> result["final_answer"]
        'Your total sales amount to $123,456.'
    """
    settings = get_settings()

    logger.info(
        "summarizing_results",
        user_query=state["user_query"],
        row_count=state.get("row_count", 0),
        has_error=bool(state.get("execution_error")),
        intent=state.get("intent"),
        thread_id=state["thread_id"],
    )

    # Initialize LLM with slight temperature for natural language
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0.3,  # Slight creativity for natural phrasing
        api_key=settings.openai_api_key.get_secret_value(),
    )

    # Format prompts based on result type
    system_prompt, user_prompt = format_summarizer_prompt(
        user_query=state["user_query"],
        query_results=state.get("query_results"),
        row_count=state.get("row_count", 0),
        execution_time_ms=state.get("execution_time_ms", 0.0),
        execution_error=state.get("execution_error"),
        intent=state.get("intent"),
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        final_answer = response.content

        logger.info(
            "summarization_complete",
            answer_length=len(final_answer),
            thread_id=state["thread_id"],
        )

        return {
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
        }

    except Exception as e:
        logger.error(
            "summarizer_error",
            error=str(e),
            thread_id=state["thread_id"],
        )
        # Fallback to a generic response
        fallback_answer = _generate_fallback_response(state)
        return {
            "final_answer": fallback_answer,
            "messages": [AIMessage(content=fallback_answer)],
        }


def _generate_fallback_response(state: RetailInsightsState) -> str:
    """Generate a fallback response when LLM invocation fails.

    Args:
        state: Current workflow state.

    Returns:
        A simple fallback message based on available data.
    """
    if state.get("execution_error"):
        return (
            "I encountered an issue processing your request. "
            "Could you try rephrasing your question?"
        )

    if state.get("query_results") and state.get("row_count", 0) > 0:
        row_count = state["row_count"]
        return (
            f"I found {row_count} result{'s' if row_count != 1 else ''} "
            "for your query. Please review the data below."
        )

    if state.get("intent") == "chat":
        return (
            "Hello! I'm your retail insights assistant. "
            "I can help you analyze sales data, orders, and more. "
            "What would you like to know?"
        )

    return (
        "I wasn't able to find any matching data for your query. "
        "Try asking about sales, orders, products, or shipping information."
    )


def create_mock_summarizer(
    final_answer: str = "This is a mock summary.",
):
    """Create a mock summarizer function for testing.

    Args:
        final_answer: The summary text to return.

    Returns:
        Async function matching summarize_results signature.
    """

    async def mock_summarize_results(state: RetailInsightsState) -> dict:
        return {
            "final_answer": final_answer,
            "messages": [AIMessage(content=final_answer)],
        }

    return mock_summarize_results
