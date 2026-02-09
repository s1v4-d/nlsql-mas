"""Unit tests for Summarizer agent node and prompts."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from retail_insights.agents.nodes.summarizer import (
    _generate_fallback_response,
    create_mock_summarizer,
    summarize_results,
)
from retail_insights.agents.prompts.summarizer import (
    MAX_RESULT_TOKENS,
    MAX_ROWS_IN_PROMPT,
    MAX_STRING_LENGTH,
    SUMMARIZER_SYSTEM_PROMPT,
    SUMMARIZER_USER_PROMPT_CHAT,
    SUMMARIZER_USER_PROMPT_DATA,
    SUMMARIZER_USER_PROMPT_EMPTY,
    SUMMARIZER_USER_PROMPT_ERROR,
    _format_row,
    _truncate_value,
    format_execution_time,
    format_results_for_prompt,
    format_summarizer_prompt,
)
from retail_insights.agents.state import create_initial_state


class TestSummarizerPrompts:
    """Tests for summarizer prompt templates."""

    def test_system_prompt_contains_result_types(self) -> None:
        """Test that system prompt handles all result types."""
        assert "data" in SUMMARIZER_SYSTEM_PROMPT
        assert "empty" in SUMMARIZER_SYSTEM_PROMPT
        assert "error" in SUMMARIZER_SYSTEM_PROMPT
        assert "chat" in SUMMARIZER_SYSTEM_PROMPT

    def test_system_prompt_has_guidelines(self) -> None:
        """Test that system prompt has response guidelines."""
        assert "Key Finding" in SUMMARIZER_SYSTEM_PROMPT
        assert "Concise" in SUMMARIZER_SYSTEM_PROMPT
        assert "Never Expose Technical Details" in SUMMARIZER_SYSTEM_PROMPT

    def test_data_prompt_has_placeholders(self) -> None:
        """Test that data prompt has all required placeholders."""
        assert "{user_query}" in SUMMARIZER_USER_PROMPT_DATA
        assert "{execution_time}" in SUMMARIZER_USER_PROMPT_DATA
        assert "{row_count}" in SUMMARIZER_USER_PROMPT_DATA
        assert "{formatted_results}" in SUMMARIZER_USER_PROMPT_DATA

    def test_empty_prompt_has_placeholders(self) -> None:
        """Test that empty prompt has required placeholders."""
        assert "{user_query}" in SUMMARIZER_USER_PROMPT_EMPTY

    def test_error_prompt_has_placeholders(self) -> None:
        """Test that error prompt has required placeholders."""
        assert "{user_query}" in SUMMARIZER_USER_PROMPT_ERROR
        assert "{error_type}" in SUMMARIZER_USER_PROMPT_ERROR
        assert "{error_details}" in SUMMARIZER_USER_PROMPT_ERROR

    def test_chat_prompt_has_placeholders(self) -> None:
        """Test that chat prompt has required placeholders."""
        assert "{user_query}" in SUMMARIZER_USER_PROMPT_CHAT


class TestTruncateValue:
    """Tests for value truncation helper."""

    def test_truncate_none(self) -> None:
        """Test truncating None value."""
        assert _truncate_value(None) == "null"

    def test_truncate_bool_true(self) -> None:
        """Test truncating True boolean."""
        assert _truncate_value(True) == "true"

    def test_truncate_bool_false(self) -> None:
        """Test truncating False boolean."""
        assert _truncate_value(False) == "false"

    def test_truncate_integer(self) -> None:
        """Test truncating integer."""
        assert _truncate_value(12345) == "12345"

    def test_truncate_float(self) -> None:
        """Test truncating float."""
        assert _truncate_value(123.45) == "123.45"

    def test_truncate_short_string(self) -> None:
        """Test that short strings are not truncated."""
        short = "Hello World"
        assert _truncate_value(short) == short

    def test_truncate_long_string(self) -> None:
        """Test that long strings are truncated with ellipsis."""
        long_string = "x" * 150
        result = _truncate_value(long_string)
        assert len(result) == MAX_STRING_LENGTH
        assert result.endswith("...")

    def test_truncate_custom_length(self) -> None:
        """Test truncation with custom max length."""
        result = _truncate_value("Hello World!", max_length=8)
        assert result == "Hello..."
        assert len(result) == 8


class TestFormatRow:
    """Tests for row formatting helper."""

    def test_format_simple_row(self) -> None:
        """Test formatting a simple row."""
        row = {"name": "Widget", "price": 9.99}
        columns = ["name", "price"]
        result = _format_row(row, columns)
        assert result == "Widget | 9.99"

    def test_format_row_with_missing_column(self) -> None:
        """Test formatting row with missing column returns null."""
        row = {"name": "Widget"}
        columns = ["name", "price"]
        result = _format_row(row, columns)
        assert result == "Widget | null"

    def test_format_row_respects_column_order(self) -> None:
        """Test that column order is respected."""
        row = {"a": 1, "b": 2, "c": 3}
        columns = ["c", "a", "b"]
        result = _format_row(row, columns)
        assert result == "3 | 1 | 2"


class TestFormatResultsForPrompt:
    """Tests for result formatting."""

    def test_format_empty_results(self) -> None:
        """Test formatting empty result set."""
        result = format_results_for_prompt([])
        assert result == "(no data)"

    def test_format_single_row(self) -> None:
        """Test formatting single row result."""
        results = [{"total_revenue": 12345.67}]
        result = format_results_for_prompt(results)
        lines = result.split("\n")
        assert "total_revenue" in lines[0]
        assert "12345.67" in lines[2]

    def test_format_multiple_rows(self) -> None:
        """Test formatting multiple rows."""
        results = [
            {"category": "Electronics", "sales": 1000},
            {"category": "Clothing", "sales": 800},
        ]
        result = format_results_for_prompt(results)
        assert "Electronics" in result
        assert "Clothing" in result
        assert "1000" in result
        assert "800" in result

    def test_format_respects_max_rows(self) -> None:
        """Test that results are truncated at max_rows."""
        results = [{"id": i} for i in range(100)]
        result = format_results_for_prompt(results, max_rows=10)
        assert "more rows" in result

    def test_format_smart_sampling(self) -> None:
        """Test smart sampling includes head and tail."""
        results = [{"id": i, "val": f"item_{i}"} for i in range(20)]
        result = format_results_for_prompt(results, max_rows=6)

        # Should have head items
        assert "item_0" in result
        assert "item_1" in result
        assert "item_2" in result

        # Should have tail items
        assert "item_17" in result
        assert "item_18" in result
        assert "item_19" in result

        # Should indicate omission
        assert "more rows" in result

    def test_format_without_header(self) -> None:
        """Test formatting without header."""
        results = [{"col": "value"}]
        result = format_results_for_prompt(results, include_header=False)
        assert "col" not in result.split("\n")[0]
        assert "value" in result


class TestFormatExecutionTime:
    """Tests for execution time formatting."""

    def test_format_microseconds(self) -> None:
        """Test formatting sub-millisecond times."""
        assert format_execution_time(0.5) == "500μs"
        assert format_execution_time(0.1) == "100μs"

    def test_format_milliseconds(self) -> None:
        """Test formatting millisecond times."""
        assert format_execution_time(100) == "100ms"
        assert format_execution_time(500) == "500ms"

    def test_format_seconds(self) -> None:
        """Test formatting second times."""
        assert format_execution_time(1000) == "1.00s"
        assert format_execution_time(2500) == "2.50s"


class TestFormatSummarizerPrompt:
    """Tests for the main prompt formatting function."""

    def test_format_data_prompt(self) -> None:
        """Test formatting prompt for data results."""
        system, user = format_summarizer_prompt(
            user_query="What are top sales?",
            query_results=[{"product": "Widget", "sales": 1000}],
            row_count=1,
            execution_time_ms=50,
        )
        assert "data" in system
        assert "What are top sales?" in user
        assert "Widget" in user
        assert "1000" in user

    def test_format_empty_prompt(self) -> None:
        """Test formatting prompt for empty results."""
        system, user = format_summarizer_prompt(
            user_query="Find products with zero sales",
            query_results=[],
            row_count=0,
        )
        assert "empty" in system
        assert "Find products with zero sales" in user

    def test_format_error_prompt(self) -> None:
        """Test formatting prompt for errors."""
        system, user = format_summarizer_prompt(
            user_query="Show sales data",
            execution_error="Column 'foo' not found",
        )
        assert "error" in system
        assert "data field issue" in user
        assert "Show sales data" in user

    def test_format_error_timeout(self) -> None:
        """Test formatting prompt for timeout errors."""
        _, user = format_summarizer_prompt(
            user_query="Complex query",
            execution_error="Query timeout exceeded",
        )
        assert "timeout" in user

    def test_format_error_syntax(self) -> None:
        """Test formatting prompt for syntax errors."""
        _, user = format_summarizer_prompt(
            user_query="Bad query",
            execution_error="Syntax error at line 1",
        )
        assert "syntax" in user

    def test_format_chat_prompt(self) -> None:
        """Test formatting prompt for chat intent."""
        system, user = format_summarizer_prompt(
            user_query="Hello there!",
            intent="chat",
        )
        assert "chat" in system
        assert "Hello there!" in user


class TestGenerateFallbackResponse:
    """Tests for fallback response generation."""

    def test_fallback_for_error(self) -> None:
        """Test fallback response when there's an execution error."""
        state = create_initial_state("Query", "thread-1")
        state["execution_error"] = "Some error"
        response = _generate_fallback_response(state)
        assert "issue" in response.lower()
        assert "rephras" in response.lower()

    def test_fallback_for_data(self) -> None:
        """Test fallback response when there's data."""
        state = create_initial_state("Query", "thread-1")
        state["query_results"] = [{"a": 1}]
        state["row_count"] = 1
        response = _generate_fallback_response(state)
        assert "1 result" in response

    def test_fallback_for_multiple_rows(self) -> None:
        """Test fallback response pluralization."""
        state = create_initial_state("Query", "thread-1")
        state["query_results"] = [{"a": 1}, {"a": 2}]
        state["row_count"] = 2
        response = _generate_fallback_response(state)
        assert "2 results" in response

    def test_fallback_for_chat(self) -> None:
        """Test fallback response for chat intent."""
        state = create_initial_state("Hi", "thread-1")
        state["intent"] = "chat"
        response = _generate_fallback_response(state)
        assert "assistant" in response.lower()

    def test_fallback_default(self) -> None:
        """Test default fallback response."""
        state = create_initial_state("Query", "thread-1")
        response = _generate_fallback_response(state)
        assert "sales" in response.lower() or "data" in response.lower()


class TestCreateMockSummarizer:
    """Tests for create_mock_summarizer helper."""

    @pytest.mark.asyncio
    async def test_mock_summarizer_default(self) -> None:
        """Test mock summarizer with default response."""
        mock_summarizer = create_mock_summarizer()
        state = create_initial_state("Test query", "thread-1")

        result = await mock_summarizer(state)

        assert result["final_answer"] == "This is a mock summary."
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_mock_summarizer_custom_answer(self) -> None:
        """Test mock summarizer with custom answer."""
        custom_answer = "Custom summary for testing."
        mock_summarizer = create_mock_summarizer(final_answer=custom_answer)
        state = create_initial_state("Test", "thread-1")

        result = await mock_summarizer(state)

        assert result["final_answer"] == custom_answer

    @pytest.mark.asyncio
    async def test_mock_summarizer_message_content(self) -> None:
        """Test that mock summarizer message matches final_answer."""
        answer = "The total is $1,234."
        mock_summarizer = create_mock_summarizer(final_answer=answer)
        state = create_initial_state("Test", "thread-1")

        result = await mock_summarizer(state)

        assert result["messages"][0].content == answer


class TestSummarizeResults:
    """Tests for the main summarize_results function."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.OPENAI_MODEL = "gpt-4o"
        settings.OPENAI_API_KEY.get_secret_value.return_value = "test-key"
        return settings

    @pytest.mark.asyncio
    async def test_summarize_results_success(self, mock_settings: MagicMock) -> None:
        """Test successful summarization with mocked LLM."""
        state = create_initial_state("What is total revenue?", "thread-1")
        state["query_results"] = [{"total_revenue": 123456.78}]
        state["row_count"] = 1
        state["execution_time_ms"] = 50

        mock_response = MagicMock()
        mock_response.content = "Your total revenue is $123,456.78."

        with (
            patch(
                "retail_insights.agents.nodes.summarizer.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.summarizer.ChatOpenAI") as mock_llm,
        ):
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await summarize_results(state)

        assert result["final_answer"] == "Your total revenue is $123,456.78."
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_summarize_results_empty(self, mock_settings: MagicMock) -> None:
        """Test summarization of empty results."""
        state = create_initial_state("Find sales with zero amount", "thread-1")
        state["query_results"] = []
        state["row_count"] = 0

        mock_response = MagicMock()
        mock_response.content = "No sales with zero amount were found."

        with (
            patch(
                "retail_insights.agents.nodes.summarizer.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.summarizer.ChatOpenAI") as mock_llm,
        ):
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await summarize_results(state)

        assert "No sales" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_summarize_results_error(self, mock_settings: MagicMock) -> None:
        """Test summarization of error state."""
        state = create_initial_state("Bad query", "thread-1")
        state["execution_error"] = "Column not found"

        mock_response = MagicMock()
        mock_response.content = "I had trouble understanding your request."

        with (
            patch(
                "retail_insights.agents.nodes.summarizer.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.summarizer.ChatOpenAI") as mock_llm,
        ):
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await summarize_results(state)

        assert result["final_answer"] is not None

    @pytest.mark.asyncio
    async def test_summarize_results_chat_intent(self, mock_settings: MagicMock) -> None:
        """Test summarization for chat intent."""
        state = create_initial_state("Hello!", "thread-1")
        state["intent"] = "chat"

        mock_response = MagicMock()
        mock_response.content = "Hello! How can I help you today?"

        with (
            patch(
                "retail_insights.agents.nodes.summarizer.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.summarizer.ChatOpenAI") as mock_llm,
        ):
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            result = await summarize_results(state)

        assert "Hello" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_summarize_results_llm_error_uses_fallback(
        self, mock_settings: MagicMock
    ) -> None:
        """Test that LLM errors trigger fallback response."""
        state = create_initial_state("Test query", "thread-1")
        state["query_results"] = [{"total": 100}]
        state["row_count"] = 1

        with (
            patch(
                "retail_insights.agents.nodes.summarizer.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.summarizer.ChatOpenAI") as mock_llm,
        ):
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(side_effect=Exception("API Error"))
            mock_llm.return_value = mock_instance

            result = await summarize_results(state)

        # Should use fallback response
        assert "1 result" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_summarize_results_logs_info(self, mock_settings: MagicMock) -> None:
        """Test that summarization logs appropriate info."""
        state = create_initial_state("Test", "thread-1")
        state["query_results"] = [{"a": 1}]
        state["row_count"] = 1

        mock_response = MagicMock()
        mock_response.content = "Summary"

        with (
            patch(
                "retail_insights.agents.nodes.summarizer.get_settings",
                return_value=mock_settings,
            ),
            patch("retail_insights.agents.nodes.summarizer.ChatOpenAI") as mock_llm,
        ):
            mock_instance = MagicMock()
            mock_instance.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm.return_value = mock_instance

            with patch("retail_insights.agents.nodes.summarizer.logger") as mock_logger:
                await summarize_results(state)
                mock_logger.info.assert_called()


class TestPromptConstants:
    """Tests for prompt module constants."""

    def test_max_result_tokens_reasonable(self) -> None:
        """Test MAX_RESULT_TOKENS is within reasonable bounds."""
        assert 1000 <= MAX_RESULT_TOKENS <= 4000

    def test_max_rows_reasonable(self) -> None:
        """Test MAX_ROWS_IN_PROMPT is within reasonable bounds."""
        assert 10 <= MAX_ROWS_IN_PROMPT <= 100

    def test_max_string_length_reasonable(self) -> None:
        """Test MAX_STRING_LENGTH is within reasonable bounds."""
        assert 50 <= MAX_STRING_LENGTH <= 200
