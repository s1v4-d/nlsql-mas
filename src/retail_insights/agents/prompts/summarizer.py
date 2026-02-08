"""Summarizer agent prompt templates.

This module defines prompts for transforming SQL query results
into human-readable narratives for end users.
"""

SUMMARIZER_SYSTEM_PROMPT = """You are a business analyst assistant for a retail sales company.

Your task is to transform SQL query results into clear, actionable insights for business users.

## Response Guidelines

### Lead with Key Findings
- Start with the most important insight
- Use specific numbers with proper formatting ($1,234.56, 1,234 units)
- Highlight trends, comparisons, or anomalies

### Be Conversational but Concise
- Use natural language, avoid technical jargon
- Keep responses to 3-5 sentences for simple queries
- Expand for complex multi-part questions

### Provide Context
- Relate numbers to business context when possible
- Mention time periods or filters that were applied
- Note any limitations in the data

### Format Numbers Properly
- Currency: $1,234.56 (include cents for small amounts)
- Large numbers: 1.2M, 45.3K
- Percentages: 23.5%
- Counts: "1,234 orders"

### Never Expose Technical Details
- Do not mention SQL queries, table names, or column names
- Do not reference database operations
- Present information as business knowledge

## Result Type Handling

### For Data Results ({result_type} = "data")
- Summarize the key findings from the data
- For single values, state the answer directly
- For tables, describe top items, totals, or patterns
- Mention row count if relevant ("showing top 10 of 156 results")

### For Empty Results ({result_type} = "empty")
- Explain that no matching data was found
- Suggest possible reasons (date range, filters, data availability)
- Offer alternative questions the user might ask

### For Error Results ({result_type} = "error")
- Provide a user-friendly error explanation
- Never show raw error messages or SQL
- Suggest how the user might rephrase their question
- Offer to help with a simpler question

### For Chat Responses ({result_type} = "chat")
- Respond conversationally
- Offer help with data questions
- Describe what kinds of questions you can answer"""

SUMMARIZER_USER_PROMPT_DATA = """## User Question
{user_query}

## Query Information
- Execution time: {execution_time}
- Rows returned: {row_count}

## Query Results
{formatted_results}

Provide a clear, business-friendly summary of these results that directly answers the user's question."""

SUMMARIZER_USER_PROMPT_EMPTY = """## User Question
{user_query}

## Query Information
The query executed successfully but returned no results.

Explain to the user why no data was found and suggest how they might modify their question to find relevant information."""

SUMMARIZER_USER_PROMPT_ERROR = """## User Question
{user_query}

## Error Information
Error type: {error_type}
Details: {error_details}

Explain to the user that we couldn't retrieve the data and suggest how they might rephrase their question. Be helpful and encouraging."""

SUMMARIZER_USER_PROMPT_CHAT = """## User Message
{user_query}

## Context
The user's message was classified as a chat/greeting rather than a data query.
You have access to retail sales data including orders, products, categories, and shipping information.

Respond conversationally and offer to help with data analysis questions."""


# Token budget for result data in prompts
MAX_RESULT_TOKENS = 2000
MAX_ROWS_IN_PROMPT = 50
MAX_STRING_LENGTH = 100


def _truncate_value(value: str | int | float | bool | None, max_length: int = MAX_STRING_LENGTH) -> str:
    """Truncate a value for display in prompts.

    Args:
        value: The value to truncate.
        max_length: Maximum string length.

    Returns:
        Truncated string representation.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    str_value = str(value)
    if len(str_value) > max_length:
        return str_value[:max_length - 3] + "..."
    return str_value


def _format_row(row: dict, columns: list[str]) -> str:
    """Format a single row for display.

    Args:
        row: Dictionary representing a row.
        columns: Ordered list of columns to display.

    Returns:
        Formatted row string.
    """
    values = [_truncate_value(row.get(col)) for col in columns]
    return " | ".join(values)


def format_results_for_prompt(
    results: list[dict],
    *,
    max_rows: int = MAX_ROWS_IN_PROMPT,
    include_header: bool = True,
) -> str:
    """Format query results for inclusion in the summarizer prompt.

    Uses smart sampling to stay within token budget while preserving
    representative data (head + tail rows for large result sets).

    Args:
        results: List of result dictionaries from query execution.
        max_rows: Maximum number of rows to include in formatted output.
        include_header: Whether to include column header row.

    Returns:
        Formatted string representation of results.
    """
    if not results:
        return "(no data)"

    columns = list(results[0].keys())
    lines = []

    # Add header
    if include_header:
        header = " | ".join(columns)
        lines.append(header)
        lines.append("-" * len(header))

    total_rows = len(results)

    if total_rows <= max_rows:
        # Include all rows
        for row in results:
            lines.append(_format_row(row, columns))
    else:
        # Smart sampling: head + tail with ellipsis
        head_count = max_rows // 2
        tail_count = max_rows - head_count

        # Head rows
        for row in results[:head_count]:
            lines.append(_format_row(row, columns))

        # Ellipsis indicator
        omitted = total_rows - max_rows
        lines.append(f"... ({omitted} more rows) ...")

        # Tail rows
        for row in results[-tail_count:]:
            lines.append(_format_row(row, columns))

    return "\n".join(lines)


def format_execution_time(time_ms: float) -> str:
    """Format execution time for display.

    Args:
        time_ms: Execution time in milliseconds.

    Returns:
        Human-readable execution time string.
    """
    if time_ms < 1:
        return f"{time_ms * 1000:.0f}μs"
    if time_ms < 1000:
        return f"{time_ms:.0f}ms"
    return f"{time_ms / 1000:.2f}s"


def format_summarizer_prompt(
    user_query: str,
    *,
    query_results: list[dict] | None = None,
    row_count: int = 0,
    execution_time_ms: float = 0.0,
    execution_error: str | None = None,
    intent: str | None = None,
) -> tuple[str, str]:
    """Format the summarizer prompt based on result type.

    Args:
        user_query: The original user question.
        query_results: Results from query execution (if successful).
        row_count: Number of rows returned.
        execution_time_ms: Query execution time in milliseconds.
        execution_error: Error message if execution failed.
        intent: Router-classified intent (query/summarize/chat).

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    # Determine result type
    if execution_error:
        result_type = "error"
    elif intent == "chat":
        result_type = "chat"
    elif not query_results or row_count == 0:
        result_type = "empty"
    else:
        result_type = "data"

    # Format system prompt with result type
    system_prompt = SUMMARIZER_SYSTEM_PROMPT.format(result_type=result_type)

    # Format user prompt based on result type
    if result_type == "data":
        formatted_results = format_results_for_prompt(query_results or [])
        execution_time = format_execution_time(execution_time_ms)
        user_prompt = SUMMARIZER_USER_PROMPT_DATA.format(
            user_query=user_query,
            execution_time=execution_time,
            row_count=row_count,
            formatted_results=formatted_results,
        )
    elif result_type == "empty":
        user_prompt = SUMMARIZER_USER_PROMPT_EMPTY.format(user_query=user_query)
    elif result_type == "error":
        # Parse error type from message
        error_type = "query error"
        if execution_error:
            if "timeout" in execution_error.lower():
                error_type = "timeout"
            elif "syntax" in execution_error.lower():
                error_type = "query syntax issue"
            elif "column" in execution_error.lower():
                error_type = "data field issue"
            elif "table" in execution_error.lower():
                error_type = "data source issue"
        user_prompt = SUMMARIZER_USER_PROMPT_ERROR.format(
            user_query=user_query,
            error_type=error_type,
            error_details=execution_error or "An unexpected error occurred",
        )
    else:  # chat
        user_prompt = SUMMARIZER_USER_PROMPT_CHAT.format(user_query=user_query)

    return system_prompt, user_prompt
