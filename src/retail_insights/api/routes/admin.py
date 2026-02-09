"""Admin API routes for schema registry management.

These routes are protected by API key authentication and provide
administrative control over the schema registry.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from retail_insights.api.auth import require_admin
from retail_insights.engine.schema_registry import SchemaRegistry, get_schema_registry
from retail_insights.models.schema import DataSource, SchemaRegistryState

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# Response models
class SchemaRefreshResponse(BaseModel):
    """Response from schema refresh operation."""

    success: bool = Field(..., description="Whether refresh succeeded")
    tables_discovered: int = Field(..., description="Number of tables discovered")
    state: SchemaRegistryState = Field(..., description="Current registry state")


class AddSourceRequest(BaseModel):
    """Request to add a new data source."""

    source: DataSource = Field(..., description="Data source to add")


class AddSourceResponse(BaseModel):
    """Response from add source operation."""

    success: bool = Field(..., description="Whether add succeeded")
    source_added: DataSource = Field(..., description="Added data source")
    message: str = Field(..., description="Status message")


class SchemaContextResponse(BaseModel):
    """Response containing schema context for prompts."""

    context: str = Field(..., description="Markdown-formatted schema context")
    tables_count: int = Field(..., description="Number of tables in context")


# Dependency to get schema registry
def get_registry() -> SchemaRegistry:
    """Get the schema registry singleton."""
    return get_schema_registry()


@router.get("/schema", response_model=SchemaRegistryState)
async def get_schema_state(
    registry: Annotated[SchemaRegistry, Depends(get_registry)],
) -> SchemaRegistryState:
    """Get current schema registry state.

    Returns:
        Current state including tables and cache status.
    """
    return registry.get_state()


@router.post("/schema/refresh", response_model=SchemaRefreshResponse)
async def refresh_schema(
    registry: Annotated[SchemaRegistry, Depends(get_registry)],
) -> SchemaRefreshResponse:
    """Force refresh of schema cache.

    This will re-discover all tables from configured data sources
    and update the cache.

    Returns:
        Refresh result with updated state.
    """
    logger.info("Admin triggered schema refresh")
    state = registry.refresh_schema()

    return SchemaRefreshResponse(
        success=True,
        tables_discovered=len(state.tables),
        state=state,
    )


@router.post("/schema/sources", response_model=AddSourceResponse)
async def add_source(
    request: AddSourceRequest,
    registry: Annotated[SchemaRegistry, Depends(get_registry)],
) -> AddSourceResponse:
    """Add a new data source to the registry.

    The source will be added and a refresh triggered to discover tables.

    Args:
        request: Data source to add.

    Returns:
        Result of adding the source.
    """
    logger.info(f"Admin adding data source: {request.source.type} - {request.source.path}")
    registry.add_source(request.source)

    return AddSourceResponse(
        success=True,
        source_added=request.source,
        message=f"Added {request.source.type} source. Call /schema/refresh to discover tables.",
    )


@router.get("/schema/context", response_model=SchemaContextResponse)
async def get_schema_context_route(
    registry: Annotated[SchemaRegistry, Depends(get_registry)],
    max_tables: int = 20,
) -> SchemaContextResponse:
    """Get schema context for SQL generation prompts.

    Args:
        max_tables: Maximum number of tables to include.

    Returns:
        Markdown-formatted schema documentation.
    """
    context = registry.get_schema_context(max_tables=max_tables)
    state = registry.get_state()

    return SchemaContextResponse(
        context=context,
        tables_count=len(state.tables),
    )


@router.get("/schema/tables", response_model=list[str])
async def get_valid_tables(
    registry: Annotated[SchemaRegistry, Depends(get_registry)],
) -> list[str]:
    """Get list of valid table names.

    Returns:
        List of table names in the registry.
    """
    return registry.get_valid_tables()


@router.get("/schema/tables/{table_name}/columns", response_model=list[str])
async def get_table_columns(
    table_name: str,
    registry: Annotated[SchemaRegistry, Depends(get_registry)],
) -> list[str]:
    """Get column names for a specific table.

    Args:
        table_name: Name of the table.

    Returns:
        List of column names.

    Raises:
        HTTPException: If table not found.
    """
    schema = registry.get_table(table_name)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found in registry",
        )

    return schema.get_column_names()
