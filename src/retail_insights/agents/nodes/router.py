"""Router agent node for intent classification.

This module implements the Router agent that classifies user queries
into appropriate workflow paths: query, summarize, chat, or clarify.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from retail_insights.agents.prompts.router import format_router_prompt
from retail_insights.agents.state import RetailInsightsState
from retail_insights.core.config import get_settings
from retail_insights.models.agents import Intent, RouterDecision

logger = structlog.get_logger(__name__)


async def route_query(state: RetailInsightsState) -> dict:
    """Classify user intent and route to appropriate workflow.

    Analyzes the user query and classifies it into one of four intents:
    - query: Analytical question requiring SQL generation
    - summarize: Request for interpretation of existing results
    - chat: General conversation or off-topic inquiry
    - clarify: Ambiguous request needing clarification

    Args:
        state: Current workflow state containing user_query and context.

    Returns:
        Dict with updates to state:
        - intent: Classified intent type
        - intent_confidence: Confidence score (0-1)
        - clarification_question: Question to ask if intent is 'clarify'

    Example:
        >>> state = create_initial_state("What were total sales?", "thread-1")
        >>> result = await route_query(state)
        >>> result["intent"]
        'query'
    """
    settings = get_settings()

    logger.info(
        "routing_query",
        user_query=state["user_query"],
        thread_id=state["thread_id"],
    )

    # Initialize LLM with structured output
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0,  # Deterministic for classification
        api_key=settings.OPENAI_API_KEY.get_secret_value(),
    )
    structured_llm = llm.with_structured_output(RouterDecision)

    # Format prompts with context
    system_prompt, user_prompt = format_router_prompt(
        user_query=state["user_query"],
        available_tables=state.get("available_tables"),
    )

    # Invoke LLM for classification
    try:
        result: RouterDecision = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )

        logger.info(
            "router_decision",
            intent=result.intent.value,
            confidence=result.confidence,
            reasoning=result.reasoning,
        )

        return {
            "intent": result.intent.value,
            "intent_confidence": result.confidence,
            "clarification_question": result.clarification_question,
        }

    except Exception as e:
        logger.error("router_error", error=str(e))
        # Default to query with low confidence on error
        return {
            "intent": Intent.QUERY.value,
            "intent_confidence": 0.5,
            "clarification_question": None,
        }


def create_mock_router(
    intent: Intent = Intent.QUERY,
    confidence: float = 0.95,
    clarification_question: str | None = None,
):
    """Create a mock router function for testing.

    Args:
        intent: The intent to return.
        confidence: The confidence score to return.
        clarification_question: Optional clarification question.

    Returns:
        Async function matching route_query signature.
    """

    async def mock_route_query(state: RetailInsightsState) -> dict:
        return {
            "intent": intent.value,
            "intent_confidence": confidence,
            "clarification_question": clarification_question,
        }

    return mock_route_query
