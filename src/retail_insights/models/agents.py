"""Agent I/O models for structured LLM outputs.

This module defines Pydantic models for agent inputs and outputs,
enabling structured output parsing with LangChain/LangGraph.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Intent(StrEnum):
    """Intent classification for user queries."""

    QUERY = "query"  # SQL query needed
    SUMMARIZE = "summarize"  # Summarization mode
    CHAT = "chat"  # General conversation
    CLARIFY = "clarify"  # Need clarification from user


class RouterDecision(BaseModel):
    """Output of the Router agent for intent classification.

    Attributes:
        intent: Classified intent of the user query.
        confidence: Confidence score for the classification (0-1).
        reasoning: Brief explanation of the routing decision.
        clarification_question: Question to ask if intent is 'clarify'.
    """

    intent: Intent = Field(..., description="Classified intent of the user query")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for classification (0-1)",
    )
    reasoning: str = Field(
        ...,
        max_length=500,
        description="Brief explanation of the routing decision",
    )
    clarification_question: str | None = Field(
        default=None,
        max_length=500,
        description="Question to ask if intent is 'clarify'",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "intent": "query",
                    "confidence": 0.95,
                    "reasoning": "User is asking for specific data about sales revenue by category",
                    "clarification_question": None,
                }
            ]
        }
    }


class SQLGenerationResult(BaseModel):
    """Output of the SQL Generator agent.

    Attributes:
        sql_query: The generated SQL query.
        explanation: Natural language explanation of what the query does.
        tables_used: List of tables referenced in the query.
        columns_used: List of columns referenced in the query.
        assumptions: Any assumptions made during generation.
    """

    sql_query: str = Field(
        ...,
        min_length=10,
        description="The generated SQL query",
    )
    explanation: str = Field(
        ...,
        max_length=1000,
        description="Natural language explanation of the query",
    )
    tables_used: list[str] = Field(
        default_factory=list,
        description="List of tables referenced in the query",
    )
    columns_used: list[str] = Field(
        default_factory=list,
        description="List of columns referenced in the query",
    )
    assumptions: str | None = Field(
        default=None,
        max_length=500,
        description="Any assumptions made during generation",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "sql_query": "SELECT Category, SUM(Amount) as revenue FROM amazon_sales GROUP BY Category ORDER BY revenue DESC LIMIT 5",
                    "explanation": "This query calculates total revenue by product category from Amazon sales and returns the top 5 categories.",
                    "tables_used": ["amazon_sales"],
                    "columns_used": ["Category", "Amount"],
                    "assumptions": "Using 'Amount' column as revenue since it represents order value in INR",
                }
            ]
        }
    }


class ValidationResult(BaseModel):
    """Output of the SQL Validator agent.

    Attributes:
        is_valid: Whether the SQL is valid and safe to execute.
        errors: List of validation errors found.
        warnings: List of non-blocking warnings.
        corrected_sql: SQL with automatic corrections (e.g., LIMIT added).
        tables_validated: Tables that were validated against schema.
        columns_validated: Columns that were validated against schema.
    """

    is_valid: bool = Field(..., description="Whether SQL is valid and safe")
    errors: list[str] = Field(
        default_factory=list,
        description="List of validation errors found",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of non-blocking warnings",
    )
    corrected_sql: str | None = Field(
        default=None,
        description="SQL with automatic corrections applied",
    )
    tables_validated: list[str] = Field(
        default_factory=list,
        description="Tables that passed schema validation",
    )
    columns_validated: list[str] = Field(
        default_factory=list,
        description="Columns that passed schema validation",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "is_valid": True,
                    "errors": [],
                    "warnings": ["LIMIT clause was added (100 rows)"],
                    "corrected_sql": "SELECT Category FROM amazon_sales LIMIT 100",
                    "tables_validated": ["amazon_sales"],
                    "columns_validated": ["Category"],
                }
            ]
        }
    }


class ExecutionResult(BaseModel):
    """Output of the Executor agent after running a query.

    Attributes:
        success: Whether the query executed successfully.
        row_count: Number of rows returned.
        columns: List of column names in the result.
        data: Query results as list of dictionaries.
        execution_time_ms: Query execution time in milliseconds.
        error_message: Error message if execution failed.
    """

    success: bool = Field(..., description="Whether query executed successfully")
    row_count: int = Field(default=0, description="Number of rows returned")
    columns: list[str] = Field(
        default_factory=list,
        description="List of column names",
    )
    data: list[dict] = Field(
        default_factory=list,
        description="Query results as list of dictionaries",
    )
    execution_time_ms: float = Field(
        default=0.0,
        description="Query execution time in milliseconds",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if execution failed",
    )


class SummarizerInput(BaseModel):
    """Input to the Summarizer agent.

    Attributes:
        user_query: Original user question.
        sql_query: SQL query that was executed.
        query_result: Result data from query execution.
        intent: The classified intent.
    """

    user_query: str = Field(..., description="Original user question")
    sql_query: str | None = Field(default=None, description="Executed SQL query")
    query_result: ExecutionResult | None = Field(
        default=None,
        description="Query execution result",
    )
    intent: Intent = Field(..., description="Classified intent")


class SummarizerOutput(BaseModel):
    """Output of the Summarizer agent.

    Attributes:
        answer: Human-readable answer to the user's question.
        confidence: Confidence in the answer accuracy.
        follow_up_suggestions: Optional suggested follow-up questions.
    """

    answer: str = Field(
        ...,
        description="Human-readable answer to the user's question",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the answer accuracy",
    )
    follow_up_suggestions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Suggested follow-up questions",
    )
