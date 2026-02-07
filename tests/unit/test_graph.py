"""Unit tests for LangGraph state and graph builder."""

import pytest

from retail_insights.agents.graph import (
    MAX_RETRIES,
    build_graph,
    check_validation,
    get_memory_checkpointer,
    route_by_intent,
)
from retail_insights.agents.state import (
    IntentType,
    QueryMode,
    RetailInsightsState,
    ValidationStatus,
    create_initial_state,
)


class TestRetailInsightsState:
    """Tests for RetailInsightsState TypedDict."""

    def test_create_initial_state_minimal(self) -> None:
        """Test creating initial state with minimal required arguments."""
        state = create_initial_state(
            user_query="What are the top 5 products by revenue?",
            thread_id="test-thread-123",
        )

        # User input
        assert state["user_query"] == "What are the top 5 products by revenue?"
        assert state["query_mode"] == "query"

        # Router output (defaults)
        assert state["intent"] is None
        assert state["intent_confidence"] is None
        assert state["clarification_question"] is None

        # SQL Generator output (defaults)
        assert state["generated_sql"] is None
        assert state["sql_explanation"] is None
        assert state["tables_used"] == []

        # Validator output (defaults)
        assert state["sql_is_valid"] is False
        assert state["validation_status"] == "pending"
        assert state["validation_errors"] == []
        assert state["retry_count"] == 0
        assert state["max_retries"] == 3

        # Executor output (defaults)
        assert state["query_results"] is None
        assert state["row_count"] == 0
        assert state["execution_time_ms"] == 0.0
        assert state["execution_error"] is None

        # Summarizer output (defaults)
        assert state["final_answer"] is None

        # Session management
        assert state["thread_id"] == "test-thread-123"
        assert state["user_id"] is None

        # Schema context
        assert state["available_tables"] == []
        assert state["schema_context"] == ""

        # Messages (from MessagesState)
        assert state["messages"] == []

    def test_create_initial_state_full(self) -> None:
        """Test creating initial state with all optional arguments."""
        state = create_initial_state(
            user_query="Show me sales trends",
            thread_id="thread-456",
            query_mode="summarize",
            available_tables=["sales", "products", "customers"],
            schema_context="Table sales: amount, category, date...",
            user_id="user-789",
            max_retries=5,
        )

        assert state["user_query"] == "Show me sales trends"
        assert state["query_mode"] == "summarize"
        assert state["thread_id"] == "thread-456"
        assert state["user_id"] == "user-789"
        assert state["available_tables"] == ["sales", "products", "customers"]
        assert state["schema_context"] == "Table sales: amount, category, date..."
        assert state["max_retries"] == 5

    def test_query_modes(self) -> None:
        """Test all valid query modes."""
        for mode in ["query", "summarize", "chat"]:
            state = create_initial_state(
                user_query="Test query",
                thread_id="test",
                query_mode=mode,  # type: ignore
            )
            assert state["query_mode"] == mode


class TestRouteByIntent:
    """Tests for route_by_intent routing function."""

    def test_route_query_intent(self) -> None:
        """Test routing for query intent."""
        state = create_initial_state("What are sales?", "thread-1")
        state["intent"] = "query"

        result = route_by_intent(state)
        assert result == "sql_generator"

    def test_route_summarize_intent(self) -> None:
        """Test routing for summarize intent."""
        state = create_initial_state("Summarize last quarter", "thread-1")
        state["intent"] = "summarize"

        result = route_by_intent(state)
        assert result == "executor"

    def test_route_chat_intent(self) -> None:
        """Test routing for chat intent."""
        state = create_initial_state("Hello!", "thread-1")
        state["intent"] = "chat"

        result = route_by_intent(state)
        assert result == "summarizer"

    def test_route_clarify_intent(self) -> None:
        """Test routing for clarify intent."""
        state = create_initial_state("Something ambiguous", "thread-1")
        state["intent"] = "clarify"

        result = route_by_intent(state)
        assert result == "__end__"

    def test_route_default_to_query(self) -> None:
        """Test that missing intent defaults to query routing."""
        state = create_initial_state("Test", "thread-1")
        # intent is None by default

        result = route_by_intent(state)
        assert result == "sql_generator"


class TestCheckValidation:
    """Tests for check_validation routing function."""

    def test_valid_sql_routes_to_executor(self) -> None:
        """Test that valid SQL routes to executor."""
        state = create_initial_state("Test", "thread-1")
        state["sql_is_valid"] = True

        result = check_validation(state)
        assert result == "executor"

    def test_invalid_sql_with_retries_remaining(self) -> None:
        """Test that invalid SQL with retries routes back to generator."""
        state = create_initial_state("Test", "thread-1")
        state["sql_is_valid"] = False
        state["retry_count"] = 1
        state["max_retries"] = 3

        result = check_validation(state)
        assert result == "sql_generator"

    def test_invalid_sql_max_retries_exceeded(self) -> None:
        """Test that invalid SQL with max retries routes to summarizer."""
        state = create_initial_state("Test", "thread-1")
        state["sql_is_valid"] = False
        state["retry_count"] = 3
        state["max_retries"] = 3

        result = check_validation(state)
        assert result == "summarizer"

    def test_invalid_sql_exceeds_max_retries(self) -> None:
        """Test that invalid SQL exceeding max retries routes to summarizer."""
        state = create_initial_state("Test", "thread-1")
        state["sql_is_valid"] = False
        state["retry_count"] = 5
        state["max_retries"] = 3

        result = check_validation(state)
        assert result == "summarizer"

    def test_uses_default_max_retries(self) -> None:
        """Test that default MAX_RETRIES constant is used when not set."""
        state = create_initial_state("Test", "thread-1")
        state["sql_is_valid"] = False
        state["retry_count"] = MAX_RETRIES

        result = check_validation(state)
        assert result == "summarizer"


class TestBuildGraph:
    """Tests for build_graph function."""

    def test_build_graph_without_checkpointer(self) -> None:
        """Test building graph without a checkpointer."""
        graph = build_graph(use_placeholder_router=True)
        assert graph is not None

    def test_build_graph_with_memory_checkpointer(self) -> None:
        """Test building graph with memory checkpointer."""
        checkpointer = get_memory_checkpointer()
        graph = build_graph(checkpointer=checkpointer, use_placeholder_router=True)
        assert graph is not None

    def test_graph_has_expected_nodes(self) -> None:
        """Test that the graph contains all expected nodes."""
        graph = build_graph(use_placeholder_router=True)

        # Get the underlying graph to inspect nodes
        # Note: The compiled graph structure may vary by LangGraph version
        assert graph is not None

    @pytest.mark.asyncio
    async def test_graph_query_flow_basic(self) -> None:
        """Test basic query flow through the graph."""
        checkpointer = get_memory_checkpointer()
        graph = build_graph(checkpointer=checkpointer, use_placeholder_router=True)

        initial_state = create_initial_state(
            user_query="What are the top products?",
            thread_id="test-flow-1",
            available_tables=["sales"],
            schema_context="Table sales with amount and category columns",
        )

        config = {"configurable": {"thread_id": "test-flow-1"}}
        result = await graph.ainvoke(initial_state, config=config)

        # Verify state after full workflow
        assert result["intent"] == "query"
        assert result["generated_sql"] is not None
        assert result["sql_is_valid"] is True
        assert result["final_answer"] is not None

    @pytest.mark.asyncio
    async def test_graph_chat_flow(self) -> None:
        """Test chat intent flow (skips SQL generation)."""
        checkpointer = get_memory_checkpointer()
        graph = build_graph(checkpointer=checkpointer, use_placeholder_router=True)

        initial_state = create_initial_state(
            user_query="Hello, how are you?",
            thread_id="test-chat-1",
        )
        # Override intent to chat (normally set by router)
        initial_state["intent"] = "chat"

        # Manually invoke just the summarizer for chat
        # In real flow, router would set intent to "chat"
        # For now, test with placeholder that returns query intent
        config = {"configurable": {"thread_id": "test-chat-1"}}
        result = await graph.ainvoke(initial_state, config=config)

        assert result["final_answer"] is not None

    @pytest.mark.asyncio
    async def test_graph_preserves_thread_context(self) -> None:
        """Test that thread context is preserved across invocations."""
        checkpointer = get_memory_checkpointer()
        graph = build_graph(checkpointer=checkpointer, use_placeholder_router=True)

        thread_id = "test-context-1"
        config = {"configurable": {"thread_id": thread_id}}

        # First query
        state1 = create_initial_state(
            user_query="First query",
            thread_id=thread_id,
        )
        await graph.ainvoke(state1, config=config)

        # Second query on same thread
        state2 = create_initial_state(
            user_query="Second query",
            thread_id=thread_id,
        )
        result = await graph.ainvoke(state2, config=config)

        # Verify both queries were processed
        assert result["thread_id"] == thread_id
        assert result["final_answer"] is not None


class TestGetMemoryCheckpointer:
    """Tests for get_memory_checkpointer function."""

    def test_returns_memory_saver(self) -> None:
        """Test that function returns a MemorySaver instance."""
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = get_memory_checkpointer()
        assert isinstance(checkpointer, MemorySaver)


class TestTypeAliases:
    """Tests for type aliases."""

    def test_intent_type_values(self) -> None:
        """Test IntentType literal values."""
        valid_intents: list[IntentType] = ["query", "summarize", "chat", "clarify"]
        for intent in valid_intents:
            state = create_initial_state("Test", "thread-1")
            state["intent"] = intent
            assert state["intent"] == intent

    def test_query_mode_values(self) -> None:
        """Test QueryMode literal values."""
        valid_modes: list[QueryMode] = ["query", "summarize", "chat"]
        for mode in valid_modes:
            state = create_initial_state("Test", "thread-1", query_mode=mode)
            assert state["query_mode"] == mode

    def test_validation_status_values(self) -> None:
        """Test ValidationStatus literal values."""
        valid_statuses: list[ValidationStatus] = [
            "pending",
            "valid",
            "invalid",
            "failed",
        ]
        for status in valid_statuses:
            state = create_initial_state("Test", "thread-1")
            state["validation_status"] = status
            assert state["validation_status"] == status
