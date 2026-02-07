"""Prompt templates for agents."""

from retail_insights.agents.prompts.router import (
    ROUTER_FEW_SHOT_EXAMPLES,
    ROUTER_SYSTEM_PROMPT,
    ROUTER_USER_PROMPT,
    format_router_prompt,
)

__all__ = [
    "ROUTER_SYSTEM_PROMPT",
    "ROUTER_USER_PROMPT",
    "ROUTER_FEW_SHOT_EXAMPLES",
    "format_router_prompt",
]
