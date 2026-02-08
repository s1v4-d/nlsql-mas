"""FastAPI dependency injection for graph and session management."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Header, Request, status

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from retail_insights.core.config import Settings
    from retail_insights.engine.schema_registry import SchemaRegistry


# Request ID context variable for tracing (moved here to avoid circular imports)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_settings(request: Request) -> Settings:
    """Retrieve settings from application state.

    Args:
        request: FastAPI request object.

    Returns:
        Application settings instance.

    Raises:
        HTTPException: If settings are not initialized.
    """
    if not hasattr(request.app.state, "settings"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application settings not initialized",
        )
    return request.app.state.settings


def get_graph(request: Request) -> CompiledStateGraph:
    """Retrieve the compiled LangGraph workflow from application state.

    The graph is built once during application startup and stored in app.state.
    This dependency provides thread-safe access to the compiled graph.

    Args:
        request: FastAPI request object.

    Returns:
        Compiled StateGraph ready for ainvoke().

    Raises:
        HTTPException: If graph is not initialized.
    """
    if not hasattr(request.app.state, "graph"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LangGraph workflow not initialized",
        )
    return request.app.state.graph


def get_schema_registry(request: Request) -> SchemaRegistry:
    """Retrieve schema registry from application state.

    Args:
        request: FastAPI request object.

    Returns:
        Schema registry instance with loaded table metadata.

    Raises:
        HTTPException: If schema registry is not initialized.
    """
    if not hasattr(request.app.state, "schema_registry"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Schema registry not initialized",
        )
    return request.app.state.schema_registry


def get_thread_id(
    session_id: str | None = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> str:
    """Generate or extract thread ID for LangGraph state management.

    Thread ID is used by LangGraph checkpointer to maintain conversation state.
    Priority: body session_id > X-Session-ID header > new UUID.

    Args:
        session_id: Session ID from request body (highest priority).
        x_session_id: Session ID from X-Session-ID header.

    Returns:
        Thread ID string for graph configuration.
    """
    if session_id:
        return session_id
    if x_session_id:
        return x_session_id
    return str(uuid.uuid4())


# Type aliases for dependency injection
GraphDep = Annotated["CompiledStateGraph", Depends(get_graph)]
SchemaRegistryDep = Annotated["SchemaRegistry", Depends(get_schema_registry)]
SettingsDep = Annotated["Settings", Depends(get_settings)]
