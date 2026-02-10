"""LLM client abstraction for model-agnostic AI operations.

This module provides a unified interface for LLM operations,
enabling easy switching between providers (OpenAI, Anthropic, etc.).
"""

from functools import lru_cache
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from retail_insights.core.config import get_settings

# Type variable for structured output models
T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Unified LLM client with structured output support.

    Provides a model-agnostic interface for LLM operations,
    with built-in support for structured (Pydantic) outputs.

    Attributes:
        model: The underlying LangChain chat model.
        model_name: Name of the model being used.

    Example:
        ```python
        from retail_insights.core.llm import get_llm_client
        from retail_insights.models.agents import SQLGenerationResult

        client = get_llm_client()

        # Simple text response
        response = await client.ainvoke("What is 2+2?")

        # Structured output
        result = await client.ainvoke_structured(
            "Generate SQL for: get all sales",
            output_schema=SQLGenerationResult,
        )
        print(result.sql_query)
        ```
    """

    def __init__(
        self,
        model: BaseChatModel | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        """Initialize the LLM client.

        Args:
            model: Optional pre-configured LangChain model.
            model_name: Model name (e.g., 'gpt-4o', 'gpt-3.5-turbo').
            temperature: Sampling temperature (0-2).
            max_tokens: Maximum tokens in response.
        """
        settings = get_settings()

        if model is not None:
            self.model = model
            self.model_name = model_name or "custom"
        else:
            self.model_name = model_name or settings.OPENAI_MODEL
            self.model = ChatOpenAI(
                model=self.model_name,
                temperature=temperature,
                max_completion_tokens=max_tokens,
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.OPENAI_TIMEOUT,
            )

    async def ainvoke(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Invoke the LLM asynchronously and return text response.

        Args:
            prompt: User prompt/question.
            system_prompt: Optional system prompt for context.
            **kwargs: Additional arguments passed to the model.

        Returns:
            str: The model's text response.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.model.ainvoke(messages, **kwargs)
        return str(response.content)

    def invoke(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Invoke the LLM synchronously and return text response.

        Args:
            prompt: User prompt/question.
            system_prompt: Optional system prompt for context.
            **kwargs: Additional arguments passed to the model.

        Returns:
            str: The model's text response.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.model.invoke(messages, **kwargs)
        return str(response.content)

    async def ainvoke_structured(
        self,
        prompt: str,
        output_schema: type[T],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> T:
        """Invoke the LLM and parse response into structured output.

        Args:
            prompt: User prompt/question.
            output_schema: Pydantic model class for structured output.
            system_prompt: Optional system prompt for context.
            **kwargs: Additional arguments passed to the model.

        Returns:
            T: Parsed response as the specified Pydantic model.

        Example:
            ```python
            result = await client.ainvoke_structured(
                "Generate SQL for top 5 products",
                output_schema=SQLGenerationResult,
            )
            ```
        """
        structured_model = self.model.with_structured_output(output_schema)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        result = await structured_model.ainvoke(messages, **kwargs)
        return result  # type: ignore

    def invoke_structured(
        self,
        prompt: str,
        output_schema: type[T],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> T:
        """Invoke the LLM synchronously with structured output.

        Args:
            prompt: User prompt/question.
            output_schema: Pydantic model class for structured output.
            system_prompt: Optional system prompt for context.
            **kwargs: Additional arguments passed to the model.

        Returns:
            T: Parsed response as the specified Pydantic model.
        """
        structured_model = self.model.with_structured_output(output_schema)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        result = structured_model.invoke(messages, **kwargs)
        return result  # type: ignore

    def with_temperature(self, temperature: float) -> "LLMClient":
        """Create a new client with different temperature.

        Args:
            temperature: New temperature value (0-2).

        Returns:
            LLMClient: New client instance with updated temperature.
        """
        settings = get_settings()
        return LLMClient(
            model_name=self.model_name,
            temperature=temperature,
            max_tokens=settings.OPENAI_MAX_TOKENS,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    """Get cached LLM client instance.

    Uses settings from environment for configuration.

    Returns:
        LLMClient: Configured LLM client.

    Example:
        ```python
        from retail_insights.core.llm import get_llm_client

        client = get_llm_client()
        response = await client.ainvoke("Hello!")
        ```
    """
    settings = get_settings()
    return LLMClient(
        model_name=settings.OPENAI_MODEL,
        temperature=settings.OPENAI_TEMPERATURE,
        max_tokens=settings.OPENAI_MAX_TOKENS,
    )
