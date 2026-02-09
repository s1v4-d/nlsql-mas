"""Schema discovery node using LLM tool calls to explore database schema."""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from retail_insights.agents.prompts.schema_discovery import format_schema_discovery_prompt
from retail_insights.agents.state import RetailInsightsState
from retail_insights.agents.tools.schema_tools import SCHEMA_TOOLS
from retail_insights.core.config import get_settings

logger = structlog.get_logger(__name__)

MAX_TOOL_ITERATIONS = 5


class SchemaDiscoveryResult(BaseModel):
    """Structured output for schema discovery completion."""

    relevant_tables: list[str] = Field(
        description="List of table names relevant to the user's question"
    )
    schema_summary: str = Field(
        description="Summary of relevant schema information for SQL generation"
    )
    reasoning: str = Field(description="Brief explanation of why these tables were selected")


async def discover_schema(state: RetailInsightsState) -> dict:
    """Discover relevant schema using LLM with tool calls.

    Implements a tool-calling loop where the LLM can explore
    the database schema before SQL generation.

    Args:
        state: Current workflow state with user_query.

    Returns:
        Dict with updates to state:
        - refined_schema_context: Schema context for relevant tables only
        - discovered_tables: List of tables the LLM selected
    """
    settings = get_settings()

    logger.info(
        "schema_discovery_started",
        user_query=state["user_query"],
        thread_id=state["thread_id"],
    )

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0,
        api_key=settings.OPENAI_API_KEY.get_secret_value(),
    )

    llm_with_tools = llm.bind_tools(SCHEMA_TOOLS)
    tool_node = ToolNode(SCHEMA_TOOLS)

    system_prompt, user_prompt = format_schema_discovery_prompt(state["user_query"])

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    discovered_tables = []
    schema_parts = []

    for iteration in range(MAX_TOOL_ITERATIONS):
        response: AIMessage = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            logger.info(
                "schema_discovery_complete",
                iterations=iteration + 1,
                discovered_tables=discovered_tables,
            )
            break

        for tool_call in response.tool_calls:
            logger.debug(
                "schema_tool_call",
                tool=tool_call["name"],
                args=tool_call.get("args", {}),
            )

            if tool_call["name"] == "get_table_schema":
                tables_arg = tool_call.get("args", {}).get("table_names", "")
                discovered_tables.extend([t.strip() for t in tables_arg.split(",")])

        tool_result = tool_node.invoke({"messages": messages})
        tool_messages = tool_result.get("messages", [])
        messages.extend(tool_messages)

        for msg in tool_messages:
            if hasattr(msg, "content") and msg.content:
                schema_parts.append(msg.content)

    else:
        logger.warning(
            "schema_discovery_max_iterations",
            max_iterations=MAX_TOOL_ITERATIONS,
        )

    discovered_tables = list(dict.fromkeys(discovered_tables))  # Dedupe, preserve order

    if schema_parts:
        refined_context = _build_refined_context(discovered_tables, schema_parts)
    else:
        refined_context = state.get("schema_context", "")
        logger.warning("schema_discovery_no_tools_used", fallback="using original context")

    return {
        "refined_schema_context": refined_context,
        "discovered_tables": discovered_tables,
    }


def _build_refined_context(tables: list[str], schema_parts: list[str]) -> str:
    lines = [
        "## Discovered Schema\n",
        f"**Relevant Tables:** {', '.join(tables) if tables else 'All tables'}\n",
    ]
    for part in schema_parts:
        if part.strip() and not part.startswith("No "):
            lines.append(part)
            lines.append("")
    return "\n".join(lines)
