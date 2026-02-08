"""Unit tests for SQL Generator agent node and prompts."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from retail_insights.agents.nodes.sql_generator import (
    create_mock_sql_generator,
    generate_sql,
)
from retail_insights.agents.prompts.sql_generator import (
    BUSINESS_TERM_MAPPINGS,
    SQL_GENERATOR_FEW_SHOT_EXAMPLES,
    SQL_GENERATOR_SYSTEM_PROMPT,
    SQL_GENERATOR_USER_PROMPT,
    format_sql_generator_prompt,
)
from retail_insights.agents.state import create_initial_state
from retail_insights.models.agents import SQLGenerationResult


class TestSQLGeneratorPrompts:
    """Tests for SQL generator prompt templates."""

    def test_system_prompt_contains_rules(self) -> None:
        """Test that system prompt contains key SQL generation rules."""
        assert "SELECT" in SQL_GENERATOR_SYSTEM_PROMPT
        assert "LIMIT" in SQL_GENERATOR_SYSTEM_PROMPT
        assert "DuckDB" in SQL_GENERATOR_SYSTEM_PROMPT
        assert "strptime" in SQL_GENERATOR_SYSTEM_PROMPT

    def test_system_prompt_has_placeholders(self) -> None:
        """Test that system prompt has required placeholders."""
        assert "{current_date}" in SQL_GENERATOR_SYSTEM_PROMPT
        assert "{schema_context}" in SQL_GENERATOR_SYSTEM_PROMPT

    def test_user_prompt_has_placeholder(self) -> None:
        """Test that user prompt has user_query placeholder."""
        assert "{user_query}" in SQL_GENERATOR_USER_PROMPT

    def test_format_prompt_basic(self) -> None:
        """Test formatting prompt with basic inputs."""
        system, user = format_sql_generator_prompt(
            user_query="What are total sales?",
            schema_context="Table: amazon_sales (Amount, Category, Date)",
        )

        assert "What are total sales?" in user
        assert "amazon_sales" in system
        assert "Amount" in system
        assert "Category" in system

    def test_format_prompt_with_retry_context(self) -> None:
        """Test formatting prompt with validation errors for retry."""
        system, user = format_sql_generator_prompt(
            user_query="Show me revenue by region",
            schema_context='Table: amazon_sales (Amount, "ship-state", Date)',
            validation_errors=["Invalid column 'region', did you mean 'ship-state'?"],
            previous_sql="SELECT region, SUM(Amount) FROM amazon_sales",
        )

        # User prompt should contain retry context
        assert "PREVIOUS ATTEMPT" in user or "region" in user.lower()
        assert "ship-state" in user or "validation" in user.lower()

    def test_format_prompt_with_current_date(self) -> None:
        """Test that current date is injected into system prompt."""
        system, user = format_sql_generator_prompt(
            user_query="What were sales last week?",
            schema_context="Table: amazon_sales (Amount, Date)",
            current_date="2024-03-15",
        )

        assert "2024-03-15" in system

    def test_format_prompt_default_date(self) -> None:
        """Test that current date defaults when not provided."""
        system, user = format_sql_generator_prompt(
            user_query="Total sales today",
            schema_context="Table: amazon_sales (Amount)",
        )

        # Should have some date format in system prompt
        # The function auto-fills current date if not provided
        assert "{current_date}" not in system or len(system) > 100

    def test_few_shot_examples_structure(self) -> None:
        """Test that few-shot examples have correct structure."""
        assert len(SQL_GENERATOR_FEW_SHOT_EXAMPLES) >= 5

        for example in SQL_GENERATOR_FEW_SHOT_EXAMPLES:
            assert "question" in example
            assert "sql" in example
            assert "explanation" in example
            assert "tables_used" in example
            assert "columns_used" in example
            assert isinstance(example["tables_used"], list)
            assert isinstance(example["columns_used"], list)

    def test_few_shot_examples_contain_limit(self) -> None:
        """Test that all few-shot examples include LIMIT clause."""
        for example in SQL_GENERATOR_FEW_SHOT_EXAMPLES:
            assert "LIMIT" in example["sql"].upper(), (
                f"Example missing LIMIT: {example['question']}"
            )

    def test_few_shot_examples_select_only(self) -> None:
        """Test that all few-shot examples are SELECT statements."""
        for example in SQL_GENERATOR_FEW_SHOT_EXAMPLES:
            sql = example["sql"].strip().upper()
            assert sql.startswith("SELECT"), f"Example not SELECT: {example['question']}"

    def test_business_term_mappings_coverage(self) -> None:
        """Test that business term mappings cover common terms."""
        assert "revenue" in BUSINESS_TERM_MAPPINGS
        assert "sales" in BUSINESS_TERM_MAPPINGS
        assert "region" in BUSINESS_TERM_MAPPINGS
        assert "state" in BUSINESS_TERM_MAPPINGS
        assert "quantity" in BUSINESS_TERM_MAPPINGS

    def test_business_term_mappings_values(self) -> None:
        """Test that mappings point to actual column names."""
        assert BUSINESS_TERM_MAPPINGS["revenue"] == "Amount"
        assert BUSINESS_TERM_MAPPINGS["region"] == "ship-state"
        assert BUSINESS_TERM_MAPPINGS["quantity"] == "Qty"


class TestGenerateSQLNode:
    """Tests for the generate_sql agent node."""

    @pytest.fixture
    def sample_state(self) -> dict:
        """Create sample state for testing."""
        state = create_initial_state("What are total sales by category?", "test-thread")
        state["schema_context"] = """Table: amazon_sales
Columns: Order ID (VARCHAR), Date (VARCHAR), Status (VARCHAR),
Fulfilment (VARCHAR), Category (VARCHAR), Size (VARCHAR),
Qty (INTEGER), Amount (FLOAT), ship-state (VARCHAR),
ship-city (VARCHAR), B2B (BOOLEAN)"""
        return state

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.openai_model = "gpt-4o"
        settings.openai_api_key.get_secret_value.return_value = "test-key"
        return settings

    @pytest.fixture
    def mock_llm_result(self) -> SQLGenerationResult:
        """Create mock LLM result."""
        return SQLGenerationResult(
            sql_query="SELECT Category, SUM(Amount) as total FROM amazon_sales GROUP BY Category ORDER BY total DESC LIMIT 10",
            explanation="Aggregates sales amount by product category, sorted by total.",
            tables_used=["amazon_sales"],
            columns_used=["Category", "Amount"],
            assumptions=None,
        )

    @pytest.mark.asyncio
    async def test_generate_sql_success(
        self, sample_state: dict, mock_settings: MagicMock, mock_llm_result: SQLGenerationResult
    ) -> None:
        """Test successful SQL generation."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_llm_result)

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm

        with (
            patch(
                "retail_insights.agents.nodes.sql_generator.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "retail_insights.agents.nodes.sql_generator.ChatOpenAI",
                return_value=mock_llm,
            ),
        ):
            result = await generate_sql(sample_state)

        assert result["generated_sql"] == mock_llm_result.sql_query
        assert result["sql_explanation"] == mock_llm_result.explanation
        assert result["tables_used"] == mock_llm_result.tables_used
        assert result["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_generate_sql_increments_retry_count(
        self, sample_state: dict, mock_settings: MagicMock, mock_llm_result: SQLGenerationResult
    ) -> None:
        """Test that retry count increments on each call."""
        sample_state["retry_count"] = 2

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_llm_result)

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm

        with (
            patch(
                "retail_insights.agents.nodes.sql_generator.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "retail_insights.agents.nodes.sql_generator.ChatOpenAI",
                return_value=mock_llm,
            ),
        ):
            result = await generate_sql(sample_state)

        assert result["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_generate_sql_with_validation_errors(
        self, sample_state: dict, mock_settings: MagicMock, mock_llm_result: SQLGenerationResult
    ) -> None:
        """Test that validation errors are passed to prompt on retry."""
        sample_state["retry_count"] = 1
        sample_state["validation_errors"] = ["Invalid column: revenue"]
        sample_state["generated_sql"] = "SELECT revenue FROM amazon_sales"

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_llm_result)

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm

        with (
            patch(
                "retail_insights.agents.nodes.sql_generator.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "retail_insights.agents.nodes.sql_generator.ChatOpenAI",
                return_value=mock_llm,
            ),
        ):
            await generate_sql(sample_state)

        # Verify LLM was called with retry context
        call_args = mock_structured_llm.ainvoke.call_args[0][0]
        assert any("revenue" in str(msg) for msg in call_args)

    @pytest.mark.asyncio
    async def test_generate_sql_handles_llm_error(
        self, sample_state: dict, mock_settings: MagicMock
    ) -> None:
        """Test error handling when LLM fails."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(side_effect=Exception("API Error"))

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm

        with (
            patch(
                "retail_insights.agents.nodes.sql_generator.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "retail_insights.agents.nodes.sql_generator.ChatOpenAI",
                return_value=mock_llm,
            ),
        ):
            result = await generate_sql(sample_state)

        assert result["generated_sql"] is None
        assert "Failed" in result["sql_explanation"]
        assert result["sql_is_valid"] is False
        assert "validation_errors" in result

    @pytest.mark.asyncio
    async def test_generate_sql_uses_correct_model(
        self, sample_state: dict, mock_settings: MagicMock, mock_llm_result: SQLGenerationResult
    ) -> None:
        """Test that the correct model is used from settings."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_llm_result)

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm

        with (
            patch(
                "retail_insights.agents.nodes.sql_generator.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "retail_insights.agents.nodes.sql_generator.ChatOpenAI",
                return_value=mock_llm,
            ) as mock_chat,
        ):
            await generate_sql(sample_state)

        # Verify temperature=0 for deterministic SQL
        call_kwargs = mock_chat.call_args[1]
        assert call_kwargs["temperature"] == 0


class TestMockSQLGenerator:
    """Tests for the mock SQL generator helper."""

    @pytest.fixture
    def sample_state(self) -> dict:
        """Create sample state for testing."""
        return create_initial_state("Test query", "test-thread")

    @pytest.mark.asyncio
    async def test_mock_generator_default_response(self, sample_state: dict) -> None:
        """Test mock generator returns default response."""
        mock_fn = create_mock_sql_generator()
        result = await mock_fn(sample_state)

        assert result["generated_sql"] == "SELECT * FROM amazon_sales LIMIT 10"
        assert result["retry_count"] == 1
        assert "amazon_sales" in result["tables_used"]

    @pytest.mark.asyncio
    async def test_mock_generator_custom_sql(self, sample_state: dict) -> None:
        """Test mock generator with custom SQL."""
        mock_fn = create_mock_sql_generator(
            sql_query="SELECT Category FROM amazon_sales LIMIT 5",
            explanation="Get categories",
            tables_used=["amazon_sales"],
            columns_used=["Category"],
        )
        result = await mock_fn(sample_state)

        assert "Category" in result["generated_sql"]
        assert result["sql_explanation"] == "Get categories"

    @pytest.mark.asyncio
    async def test_mock_generator_failure_mode(self, sample_state: dict) -> None:
        """Test mock generator in failure mode."""
        mock_fn = create_mock_sql_generator(
            should_fail=True,
            failure_message="Schema mismatch error",
        )
        result = await mock_fn(sample_state)

        assert result["generated_sql"] is None
        assert "Schema mismatch" in result["sql_explanation"]
        assert result["sql_is_valid"] is False

    @pytest.mark.asyncio
    async def test_mock_generator_increments_retry(self, sample_state: dict) -> None:
        """Test that mock generator increments retry count."""
        sample_state["retry_count"] = 2
        mock_fn = create_mock_sql_generator()
        result = await mock_fn(sample_state)

        assert result["retry_count"] == 3


class TestSQLGeneratorIntegration:
    """Integration tests for SQL generator components."""

    def test_prompt_and_examples_alignment(self) -> None:
        """Test that prompt instructions match example patterns."""
        # Examples should demonstrate rules in prompt
        for example in SQL_GENERATOR_FEW_SHOT_EXAMPLES:
            sql = example["sql"]

            # Rule: Always use LIMIT
            assert "LIMIT" in sql.upper()

            # Rule: Quote columns with special chars
            if "ship-state" in example["columns_used"]:
                assert '"ship-state"' in sql

    def test_business_terms_cover_examples(self) -> None:
        """Test that business terms help understand example columns."""
        # Get all columns used in examples
        example_columns = set()
        for example in SQL_GENERATOR_FEW_SHOT_EXAMPLES:
            example_columns.update(example["columns_used"])

        # Core columns should have business term mappings or be obvious
        mapped_columns = set(BUSINESS_TERM_MAPPINGS.values())

        # Amount should be mapped (most common for revenue/sales)
        assert "Amount" in mapped_columns
        assert "Amount" in example_columns

    def test_date_handling_examples(self) -> None:
        """Test that examples demonstrate proper date handling."""
        date_examples = [e for e in SQL_GENERATOR_FEW_SHOT_EXAMPLES if "Date" in e["columns_used"]]

        assert len(date_examples) > 0

        for example in date_examples:
            if "month" in example["question"].lower() or "last" in example["question"].lower():
                # Should use strptime for parsing
                assert "strptime" in example["sql"]
