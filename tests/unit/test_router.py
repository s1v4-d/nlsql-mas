"""Unit tests for Router agent node and prompts."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from retail_insights.agents.nodes.router import create_mock_router, route_query
from retail_insights.agents.prompts.router import (
    ROUTER_FEW_SHOT_EXAMPLES,
    ROUTER_SYSTEM_PROMPT,
    ROUTER_USER_PROMPT,
    format_router_prompt,
)
from retail_insights.agents.state import create_initial_state
from retail_insights.models.agents import Intent, RouterDecision


class TestRouterPrompts:
    """Tests for router prompt templates."""

    def test_router_system_prompt_contains_intents(self) -> None:
        """Test that system prompt contains all intent categories."""
        assert "query" in ROUTER_SYSTEM_PROMPT
        assert "summarize" in ROUTER_SYSTEM_PROMPT
        assert "chat" in ROUTER_SYSTEM_PROMPT
        assert "clarify" in ROUTER_SYSTEM_PROMPT

    def test_router_system_prompt_has_placeholder(self) -> None:
        """Test that system prompt has available_tables placeholder."""
        assert "{available_tables}" in ROUTER_SYSTEM_PROMPT

    def test_router_user_prompt_has_placeholder(self) -> None:
        """Test that user prompt has user_query placeholder."""
        assert "{user_query}" in ROUTER_USER_PROMPT

    def test_format_router_prompt_basic(self) -> None:
        """Test formatting prompt with basic query."""
        system, user = format_router_prompt(
            user_query="What are the top products?",
        )

        assert "What are the top products?" in user
        assert "No specific tables loaded" in system

    def test_format_router_prompt_with_tables(self) -> None:
        """Test formatting prompt with available tables."""
        system, user = format_router_prompt(
            user_query="Show me sales data",
            available_tables=["sales", "products", "customers"],
        )

        assert "sales, products, customers" in system
        assert "Show me sales data" in user

    def test_format_router_prompt_empty_tables(self) -> None:
        """Test formatting prompt with empty table list."""
        system, user = format_router_prompt(
            user_query="Hello!",
            available_tables=[],
        )

        assert "No specific tables loaded" in system

    def test_few_shot_examples_structure(self) -> None:
        """Test that few-shot examples have required fields."""
        for example in ROUTER_FEW_SHOT_EXAMPLES:
            assert "query" in example
            assert "intent" in example
            assert "confidence" in example
            assert "reasoning" in example

    def test_few_shot_examples_cover_all_intents(self) -> None:
        """Test that examples cover all intent types."""
        intents = {ex["intent"] for ex in ROUTER_FEW_SHOT_EXAMPLES}
        assert "query" in intents
        assert "summarize" in intents
        assert "chat" in intents
        assert "clarify" in intents


class TestCreateMockRouter:
    """Tests for create_mock_router helper."""

    @pytest.mark.asyncio
    async def test_mock_router_default_intent(self) -> None:
        """Test mock router returns query intent by default."""
        mock_router = create_mock_router()
        state = create_initial_state("Test query", "thread-1")

        result = await mock_router(state)

        assert result["intent"] == "query"
        assert result["intent_confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_mock_router_custom_intent(self) -> None:
        """Test mock router with custom intent."""
        mock_router = create_mock_router(
            intent=Intent.CHAT,
            confidence=0.8,
        )
        state = create_initial_state("Hello!", "thread-1")

        result = await mock_router(state)

        assert result["intent"] == "chat"
        assert result["intent_confidence"] == 0.8

    @pytest.mark.asyncio
    async def test_mock_router_with_clarification(self) -> None:
        """Test mock router with clarification question."""
        mock_router = create_mock_router(
            intent=Intent.CLARIFY,
            confidence=0.7,
            clarification_question="Which report do you want?",
        )
        state = create_initial_state("Show me the report", "thread-1")

        result = await mock_router(state)

        assert result["intent"] == "clarify"
        assert result["clarification_question"] == "Which report do you want?"


class TestRouteQuery:
    """Tests for route_query function with mocked LLM."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.openai_model = "gpt-4o"
        settings.openai_api_key.get_secret_value.return_value = "test-key"
        return settings

    @pytest.fixture
    def mock_router_decision(self) -> RouterDecision:
        """Create a mock router decision."""
        return RouterDecision(
            intent=Intent.QUERY,
            confidence=0.95,
            reasoning="User is asking about sales data",
            clarification_question=None,
        )

    @pytest.mark.asyncio
    async def test_route_query_returns_query_intent(
        self,
        mock_settings: MagicMock,
        mock_router_decision: RouterDecision,
    ) -> None:
        """Test route_query classifies data query correctly."""
        state = create_initial_state(
            "What were total sales last month?",
            "thread-1",
            available_tables=["sales"],
        )

        with (
            patch(
                "retail_insights.agents.nodes.router.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.router.ChatOpenAI") as mock_chat,
        ):
            mock_structured = AsyncMock(return_value=mock_router_decision)
            mock_chat.return_value.with_structured_output.return_value.ainvoke = mock_structured

            result = await route_query(state)

            assert result["intent"] == "query"
            assert result["intent_confidence"] == 0.95
            assert result["clarification_question"] is None

    @pytest.mark.asyncio
    async def test_route_query_returns_chat_intent(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test route_query classifies chat correctly."""
        state = create_initial_state("Hello, how are you?", "thread-1")

        chat_decision = RouterDecision(
            intent=Intent.CHAT,
            confidence=0.92,
            reasoning="User is greeting, not asking for data",
            clarification_question=None,
        )

        with (
            patch(
                "retail_insights.agents.nodes.router.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.router.ChatOpenAI") as mock_chat,
        ):
            mock_structured = AsyncMock(return_value=chat_decision)
            mock_chat.return_value.with_structured_output.return_value.ainvoke = mock_structured

            result = await route_query(state)

            assert result["intent"] == "chat"
            assert result["intent_confidence"] == 0.92

    @pytest.mark.asyncio
    async def test_route_query_returns_clarify_intent(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test route_query handles ambiguous queries."""
        state = create_initial_state("Show me the report", "thread-1")

        clarify_decision = RouterDecision(
            intent=Intent.CLARIFY,
            confidence=0.75,
            reasoning="Unclear which report is requested",
            clarification_question="Which report would you like to see?",
        )

        with (
            patch(
                "retail_insights.agents.nodes.router.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.router.ChatOpenAI") as mock_chat,
        ):
            mock_structured = AsyncMock(return_value=clarify_decision)
            mock_chat.return_value.with_structured_output.return_value.ainvoke = mock_structured

            result = await route_query(state)

            assert result["intent"] == "clarify"
            assert result["clarification_question"] == "Which report would you like to see?"

    @pytest.mark.asyncio
    async def test_route_query_handles_llm_error(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test route_query falls back on LLM error."""
        state = create_initial_state("Test query", "thread-1")

        with (
            patch(
                "retail_insights.agents.nodes.router.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.router.ChatOpenAI") as mock_chat,
        ):
            mock_chat.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
                side_effect=Exception("API error")
            )

            result = await route_query(state)

            # Should fall back to query with low confidence
            assert result["intent"] == "query"
            assert result["intent_confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_route_query_returns_summarize_intent(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test route_query classifies summarization request."""
        state = create_initial_state("Explain these numbers", "thread-1")

        summarize_decision = RouterDecision(
            intent=Intent.SUMMARIZE,
            confidence=0.88,
            reasoning="User is asking for interpretation of results",
            clarification_question=None,
        )

        with (
            patch(
                "retail_insights.agents.nodes.router.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.router.ChatOpenAI") as mock_chat,
        ):
            mock_structured = AsyncMock(return_value=summarize_decision)
            mock_chat.return_value.with_structured_output.return_value.ainvoke = mock_structured

            result = await route_query(state)

            assert result["intent"] == "summarize"
            assert result["intent_confidence"] == 0.88


class TestRouterIntegration:
    """Integration tests for router with graph."""

    @pytest.mark.asyncio
    async def test_router_integrates_with_graph(self) -> None:
        """Test that router node works within graph context."""
        from retail_insights.agents.graph import build_graph, get_memory_checkpointer

        # Build graph with placeholder router (no LLM calls)
        checkpointer = get_memory_checkpointer()
        graph = build_graph(checkpointer=checkpointer, use_placeholder_router=True)

        state = create_initial_state(
            "What are the top products?",
            "test-integration-1",
            available_tables=["sales"],
        )

        config = {"configurable": {"thread_id": "test-integration-1"}}
        result = await graph.ainvoke(state, config=config)

        # Placeholder router defaults to query intent
        assert result["intent"] == "query"
        assert result["final_answer"] is not None
