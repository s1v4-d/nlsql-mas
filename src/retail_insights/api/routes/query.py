"""Query and summarize endpoints for the Retail Insights API.

This module provides the main query endpoints that invoke the LangGraph
multi-agent workflow to process natural language queries against sales data.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from retail_insights.agents import create_initial_state
from retail_insights.api.dependencies import (
    GraphDep,
    SchemaRegistryDep,
    get_thread_id,
    request_id_ctx,
)
from retail_insights.core.exceptions import ExecutionError, SQLGenerationError
from retail_insights.models.requests import QueryRequest, SummarizeRequest
from retail_insights.models.responses import ErrorResponse, QueryResult, SummaryResult

if TYPE_CHECKING:

    pass

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post(
    "/query",
    response_model=QueryResult,
    responses={
        422: {"model": ErrorResponse, "description": "Validation error or SQL generation failed"},
        500: {"model": ErrorResponse, "description": "Query execution error"},
    },
)
async def process_query(
    body: QueryRequest,
    graph: GraphDep,
    schema_registry: SchemaRegistryDep,
    x_session_id: str | None = Header(default=None),
) -> QueryResult:
    """Process a natural language query using the multi-agent workflow.

    The query is processed through the following agents:
    1. Router: Classifies intent (query/summarize/chat/clarify)
    2. SQL Generator: Generates SQL from natural language
    3. Validator: Validates SQL syntax and safety
    4. Executor: Runs the query against DuckDB
    5. Summarizer: Generates human-readable response

    Args:
        body: Query request with question, mode, and optional session_id.
        graph: Compiled LangGraph workflow (injected).
        schema_registry: Schema registry with table metadata (injected).
        x_session_id: Optional session ID from header.

    Returns:
        QueryResult with answer, SQL query, data, and execution time.

    Raises:
        HTTPException: If query processing fails.
    """
    start_time = time.perf_counter()
    thread_id = get_thread_id(body.session_id, x_session_id)
    request_id = request_id_ctx.get()

    logger.info(
        "Processing query",
        extra={
            "request_id": request_id,
            "thread_id": thread_id,
            "question": body.question[:100],
            "mode": body.mode,
        },
    )

    # Get schema context for SQL generation
    schema_context = schema_registry.get_schema_for_prompt()
    available_tables = list(schema_registry.get_table_info().keys())

    # Create initial state
    initial_state = create_initial_state(
        user_query=body.question,
        thread_id=thread_id,
        query_mode=body.mode.value,
        available_tables=available_tables,
        schema_context=schema_context,
    )

    # Invoke the graph
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except RecursionError as e:
        logger.error("Graph recursion limit exceeded", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query processing failed: too many retries or complex query",
        ) from e
    except Exception as e:
        logger.exception("Graph invocation failed", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {e!s}",
        ) from e

    execution_time_ms = (time.perf_counter() - start_time) * 1000

    # Extract result fields
    final_answer = result.get("final_answer", "No answer generated")
    sql_query = result.get("generated_sql")
    query_results = result.get("query_results")
    row_count = result.get("row_count", 0)
    execution_error = result.get("execution_error")

    # Handle execution errors
    if execution_error and not final_answer:
        raise ExecutionError(
            message=f"Query execution failed: {execution_error}",
            sql=sql_query or "",
            original_error=execution_error,
        )

    # Handle SQL generation failures
    validation_status = result.get("validation_status")
    if validation_status == "failed" and not result.get("sql_is_valid"):
        raise SQLGenerationError(
            message="Failed to generate valid SQL after retries",
            user_query=body.question,
            attempts=result.get("retry_count", 0),
            last_error=str(result.get("validation_errors", [])),
        )

    logger.info(
        "Query completed",
        extra={
            "request_id": request_id,
            "thread_id": thread_id,
            "row_count": row_count,
            "execution_time_ms": execution_time_ms,
        },
    )

    return QueryResult(
        success=True,
        answer=final_answer,
        sql_query=sql_query,
        data=query_results if isinstance(query_results, list) else None,
        row_count=row_count,
        execution_time_ms=execution_time_ms,
        session_id=thread_id,
    )


@router.post(
    "/query/stream",
    responses={
        200: {"description": "Server-sent events stream"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Execution error"},
    },
)
async def process_query_stream(
    body: QueryRequest,
    graph: GraphDep,
    schema_registry: SchemaRegistryDep,
    x_session_id: str | None = Header(default=None),
) -> StreamingResponse:
    """Process a query and stream agent updates via Server-Sent Events.

    Streams real-time updates as each agent in the workflow completes.
    Final event contains the complete QueryResult.

    Event format:
        event: agent_update
        data: {"agent": "router", "status": "completed", "intent": "query"}

        event: result
        data: {"success": true, "answer": "...", ...}

    Args:
        body: Query request with question, mode, and optional session_id.
        graph: Compiled LangGraph workflow (injected).
        schema_registry: Schema registry with table metadata (injected).
        x_session_id: Optional session ID from header.

    Returns:
        StreamingResponse with SSE events.
    """
    thread_id = get_thread_id(body.session_id, x_session_id)
    request_id = request_id_ctx.get()

    # Get schema context
    schema_context = schema_registry.get_schema_for_prompt()
    available_tables = list(schema_registry.get_table_info().keys())

    # Create initial state
    initial_state = create_initial_state(
        user_query=body.question,
        thread_id=thread_id,
        query_mode=body.mode.value,
        available_tables=available_tables,
        schema_context=schema_context,
    )

    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from graph stream."""
        import json

        start_time = time.perf_counter()

        try:
            async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    # Format SSE event
                    update = {
                        "agent": node_name,
                        "status": "completed",
                        "request_id": request_id,
                    }

                    # Include relevant info based on agent
                    if node_name == "router":
                        update["intent"] = node_output.get("intent")
                        update["confidence"] = node_output.get("intent_confidence")
                    elif node_name == "sql_generator":
                        update["sql_preview"] = (node_output.get("generated_sql") or "")[:100]
                    elif node_name == "validator":
                        update["is_valid"] = node_output.get("sql_is_valid")
                        update["validation_status"] = node_output.get("validation_status")
                    elif node_name == "executor":
                        update["row_count"] = node_output.get("row_count", 0)
                    elif node_name == "summarizer":
                        update["has_answer"] = bool(node_output.get("final_answer"))

                    yield f"event: agent_update\ndata: {json.dumps(update)}\n\n"

            # Stream completed - get final state
            final_state = await graph.aget_state(config)
            state_values = final_state.values

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            result = QueryResult(
                success=True,
                answer=state_values.get("final_answer", "No answer generated"),
                sql_query=state_values.get("generated_sql"),
                data=state_values.get("query_results"),
                row_count=state_values.get("row_count", 0),
                execution_time_ms=execution_time_ms,
                session_id=thread_id,
            )

            yield f"event: result\ndata: {result.model_dump_json()}\n\n"

        except RecursionError:
            error = ErrorResponse(
                error_code="RECURSION_ERROR",
                message="Query processing failed: too many retries",
            )
            yield f"event: error\ndata: {error.model_dump_json()}\n\n"
        except Exception as e:
            logger.exception("Stream processing failed", extra={"request_id": request_id})
            error = ErrorResponse(
                error_code="STREAM_ERROR",
                message=f"Stream processing failed: {e!s}",
            )
            yield f"event: error\ndata: {error.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "X-Request-ID": request_id,
        },
    )


@router.post(
    "/summarize",
    response_model=SummaryResult,
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Summary generation error"},
    },
)
async def generate_summary(
    body: SummarizeRequest,
    graph: GraphDep,
    schema_registry: SchemaRegistryDep,
    x_session_id: str | None = Header(default=None),
) -> SummaryResult:
    """Generate an automated sales summary for a time period.

    Uses predefined queries to gather key metrics and generates
    a human-readable summary with trend analysis.

    Args:
        body: Summary request with time_period, region, and category filters.
        graph: Compiled LangGraph workflow (injected).
        schema_registry: Schema registry with table metadata (injected).
        x_session_id: Optional session ID from header.

    Returns:
        SummaryResult with narrative summary and key metrics.
    """
    start_time = time.perf_counter()
    thread_id = get_thread_id(None, x_session_id)
    request_id = request_id_ctx.get()

    # Build summarization query from parameters
    query_parts = [f"Generate a sales summary for {body.time_period}"]
    if body.region:
        query_parts.append(f"in {body.region}")
    if body.category:
        query_parts.append(f"for {body.category} category")
    if body.include_trends:
        query_parts.append("including trend analysis")

    summary_query = " ".join(query_parts) + "."

    logger.info(
        "Generating summary",
        extra={
            "request_id": request_id,
            "thread_id": thread_id,
            "time_period": body.time_period,
            "region": body.region,
            "category": body.category,
        },
    )

    # Get schema context
    schema_context = schema_registry.get_schema_for_prompt()
    available_tables = list(schema_registry.get_table_info().keys())

    # Create initial state with summarize mode
    initial_state = create_initial_state(
        user_query=summary_query,
        thread_id=thread_id,
        query_mode="summarize",
        available_tables=available_tables,
        schema_context=schema_context,
    )

    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as e:
        logger.exception("Summary generation failed", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Summary generation failed: {e!s}",
        ) from e

    execution_time_ms = (time.perf_counter() - start_time) * 1000

    # Extract summary content
    final_answer = result.get("final_answer", "Summary not available")
    query_results = result.get("query_results", [])

    # Extract key metrics from results
    key_metrics: dict[str, Any] = {}
    if isinstance(query_results, list) and query_results:
        first_row = query_results[0]
        key_metrics = {k: v for k, v in first_row.items() if isinstance(v, (int, float, str))}

    # Build trends if requested
    trends: dict[str, Any] | None = None
    if body.include_trends and isinstance(query_results, list) and len(query_results) > 1:
        trends = {"data_points": len(query_results), "trend_available": True}

    logger.info(
        "Summary completed",
        extra={
            "request_id": request_id,
            "execution_time_ms": execution_time_ms,
        },
    )

    return SummaryResult(
        success=True,
        summary=final_answer,
        key_metrics=key_metrics,
        trends=trends,
        time_period=body.time_period,
        execution_time_ms=execution_time_ms,
    )
