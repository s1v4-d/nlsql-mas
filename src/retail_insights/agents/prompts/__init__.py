"""Prompt templates for agents."""

from retail_insights.agents.prompts.router import (
    ROUTER_FEW_SHOT_EXAMPLES,
    ROUTER_SYSTEM_PROMPT,
    ROUTER_USER_PROMPT,
    format_router_prompt,
)
from retail_insights.agents.prompts.sql_generator import (
    BUSINESS_TERM_MAPPINGS,
    SQL_GENERATOR_FEW_SHOT_EXAMPLES,
    SQL_GENERATOR_SYSTEM_PROMPT,
    SQL_GENERATOR_USER_PROMPT,
    format_sql_generator_prompt,
)
from retail_insights.agents.prompts.summarizer import (
    MAX_RESULT_TOKENS,
    MAX_ROWS_IN_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    SUMMARIZER_USER_PROMPT_CHAT,
    SUMMARIZER_USER_PROMPT_DATA,
    SUMMARIZER_USER_PROMPT_EMPTY,
    SUMMARIZER_USER_PROMPT_ERROR,
    format_execution_time,
    format_results_for_prompt,
    format_summarizer_prompt,
)

__all__ = [
    "ROUTER_SYSTEM_PROMPT",
    "ROUTER_USER_PROMPT",
    "ROUTER_FEW_SHOT_EXAMPLES",
    "format_router_prompt",
    "SQL_GENERATOR_SYSTEM_PROMPT",
    "SQL_GENERATOR_USER_PROMPT",
    "SQL_GENERATOR_FEW_SHOT_EXAMPLES",
    "BUSINESS_TERM_MAPPINGS",
    "format_sql_generator_prompt",
    "SUMMARIZER_SYSTEM_PROMPT",
    "SUMMARIZER_USER_PROMPT_DATA",
    "SUMMARIZER_USER_PROMPT_EMPTY",
    "SUMMARIZER_USER_PROMPT_ERROR",
    "SUMMARIZER_USER_PROMPT_CHAT",
    "MAX_RESULT_TOKENS",
    "MAX_ROWS_IN_PROMPT",
    "format_summarizer_prompt",
    "format_results_for_prompt",
    "format_execution_time",
]
