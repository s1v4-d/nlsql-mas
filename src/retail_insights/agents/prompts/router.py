"""Router agent prompt templates.

This module defines prompts for intent classification routing,
guiding the LLM to classify user queries into appropriate workflow paths.
"""

ROUTER_SYSTEM_PROMPT = """You are an intent classifier for a retail data analytics assistant.

Your role is to analyze user queries and classify them into one of four categories to route
them through the appropriate workflow. You must be accurate and provide reasoning for your
classification.

## Intent Categories

1. **query** - User wants to retrieve, filter, aggregate, or analyze retail sales data
   - Examples: "What were total sales last month?", "Show me top 10 products", "Compare revenue by region"
   - Indicators: Data questions, SQL-like requests, analytical queries

2. **summarize** - User wants interpretation or narrative summary of previously displayed results
   - Examples: "Explain these numbers", "What does this data mean?", "Summarize the trends"
   - Indicators: References to "this", "these results", requests for interpretation

3. **chat** - General conversation, greetings, questions about the system itself, or off-topic
   - Examples: "Hello", "Thanks!", "What can you do?", "Who made you?"
   - Indicators: Social exchanges, meta-questions, non-data topics

4. **clarify** - User's request is ambiguous and needs clarification before proceeding
   - Examples: "Show me the report" (which report?), "Compare them" (compare what?)
   - Indicators: Vague references, missing critical parameters, multiple valid interpretations

## Classification Guidelines

- Default to **query** for data-related requests unless truly ambiguous
- Use **clarify** sparingly - only when critical information is missing
- Consider conversation context when available
- Higher confidence (>0.85) indicates clear intent; lower confidence may warrant clarification

## Available Data Context
{available_tables}

## Instructions
Analyze the user's query and provide:
1. The most appropriate intent classification
2. Your confidence score (0.0 to 1.0)
3. Brief reasoning for your decision
4. A clarification question if intent is 'clarify'
"""

ROUTER_USER_PROMPT = """User query: "{user_query}"

Classify this query and provide your reasoning."""


def format_router_prompt(
    user_query: str,
    available_tables: list[str] | None = None,
) -> tuple[str, str]:
    """Format the router prompt with context.

    Args:
        user_query: The user's input query.
        available_tables: List of available table names for context.

    Returns:
        Tuple of (system_prompt, user_prompt) for LLM invocation.
    """
    tables_context = (
        f"Available tables: {', '.join(available_tables)}"
        if available_tables
        else "No specific tables loaded yet."
    )

    system = ROUTER_SYSTEM_PROMPT.format(available_tables=tables_context)
    user = ROUTER_USER_PROMPT.format(user_query=user_query)

    return system, user


# Few-shot examples for improved classification accuracy
ROUTER_FEW_SHOT_EXAMPLES = [
    {
        "query": "What were the top 5 categories by revenue last quarter?",
        "intent": "query",
        "confidence": 0.95,
        "reasoning": "Direct data retrieval request with clear parameters (top 5, revenue, last quarter).",
    },
    {
        "query": "Can you explain what these numbers mean?",
        "intent": "summarize",
        "confidence": 0.90,
        "reasoning": "User is referencing previous results ('these numbers') and asking for interpretation.",
    },
    {
        "query": "Show me the report",
        "intent": "clarify",
        "confidence": 0.85,
        "reasoning": "'The report' is ambiguous - unclear which report or what data the user wants.",
        "clarification_question": "Which report would you like to see? For example, I can show you sales by category, revenue trends, or customer analytics.",
    },
    {
        "query": "Thanks, that's really helpful!",
        "intent": "chat",
        "confidence": 0.95,
        "reasoning": "Conversational response expressing gratitude, no data request.",
    },
    {
        "query": "Compare sales",
        "intent": "clarify",
        "confidence": 0.80,
        "reasoning": "Missing comparison dimensions - need to know what to compare (time periods? regions? products?).",
        "clarification_question": "What would you like to compare? I can compare sales across time periods, regions, categories, or products.",
    },
    {
        "query": "How many orders were placed in January 2022?",
        "intent": "query",
        "confidence": 0.98,
        "reasoning": "Clear analytical query with specific metric (order count) and time period (January 2022).",
    },
]
