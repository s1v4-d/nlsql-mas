"""Schema discovery tools for LangGraph SQL agent."""

from __future__ import annotations

import structlog
from langchain_core.tools import tool

from retail_insights.engine.schema_registry import get_schema_registry

logger = structlog.get_logger(__name__)

_description_cache: dict[str, str] = {}


@tool
def list_tables() -> str:
    """List all available tables with row counts and date ranges."""
    registry = get_schema_registry()
    schemas = registry.get_schema()

    if not schemas:
        return "No tables found in the database."

    lines = ["Available tables:\n"]

    for table_name, schema in schemas.items():
        info_parts = [f"- **{table_name}**"]

        if schema.row_count:
            info_parts.append(f"({schema.row_count:,} rows)")

        if schema.date_range_start and schema.date_range_end:
            info_parts.append(f"[{schema.date_range_start} to {schema.date_range_end}]")

        description = _get_table_description(table_name)
        if description:
            info_parts.append(f"- {description}")

        lines.append(" ".join(info_parts))

    lines.append("\nUse get_table_schema with comma-separated table names to see detailed columns.")

    return "\n".join(lines)


@tool
def get_table_schema(table_names: str) -> str:
    """Get columns, types, and sample values for specified tables (comma-separated)."""
    registry = get_schema_registry()
    tables = [t.strip() for t in table_names.split(",")]

    results = []

    for table_name in tables:
        schema = registry.get_table(table_name)

        if schema is None:
            # Try case-insensitive match
            all_tables = registry.get_valid_tables()
            matches = [t for t in all_tables if t.lower() == table_name.lower()]
            if matches:
                schema = registry.get_table(matches[0])
                table_name = matches[0]

        if schema is None:
            results.append(
                f"Table '{table_name}' not found. Use list_tables to see available tables."
            )
            continue

        lines = [f"## {table_name}"]

        if schema.row_count:
            lines.append(f"Rows: ~{schema.row_count:,}")

        if schema.date_range_start and schema.date_range_end:
            lines.append(
                f"Date Range: {schema.date_range_start} to {schema.date_range_end} "
                f"(column: `{schema.date_column}`)"
            )

        lines.append("\n| Column | Type | Sample Values |")
        lines.append("|--------|------|---------------|")

        for col in schema.columns:
            samples = ", ".join(str(s) for s in col.sample_values[:3]) if col.sample_values else "-"
            if len(samples) > 50:
                samples = samples[:47] + "..."
            lines.append(f"| {col.name} | {col.data_type} | {samples} |")

        results.append("\n".join(lines))

    return "\n\n".join(results)


@tool
def search_columns(keyword: str) -> str:
    """Search for columns matching a keyword across all tables."""
    registry = get_schema_registry()
    schemas = registry.get_schema()
    keyword_lower = keyword.lower()

    matches = []

    for table_name, schema in schemas.items():
        for col in schema.columns:
            if keyword_lower in col.name.lower():
                matches.append(
                    {
                        "table": table_name,
                        "column": col.name,
                        "type": col.data_type,
                        "samples": col.sample_values[:2] if col.sample_values else [],
                    }
                )

    if not matches:
        return f"No columns found matching '{keyword}'. Try different keywords or use list_tables."

    lines = [f"Columns matching '{keyword}':\n"]
    for m in matches:
        samples = ", ".join(str(s) for s in m["samples"]) if m["samples"] else ""
        lines.append(
            f"- **{m['table']}**.{m['column']} ({m['type']}) {f'e.g., {samples}' if samples else ''}"
        )

    return "\n".join(lines)


def _get_table_description(table_name: str) -> str:
    if table_name in _description_cache:
        return _description_cache[table_name]

    try:
        from retail_insights.engine.description_generator import get_description_generator

        registry = get_schema_registry()
        schema = registry.get_table(table_name)

        if schema is None:
            return ""

        generator = get_description_generator()
        result = generator.get_description(table_name, schema)
        _description_cache[table_name] = result.table_description
        return result.table_description

    except Exception as e:
        logger.debug("description_generation_skipped", table=table_name, reason=str(e))
        return _get_fallback_description(table_name)


def _get_fallback_description(table_name: str) -> str:
    """Fallback descriptions when LLM is unavailable."""
    fallbacks = {
        "Amazon Sale Report": "Amazon marketplace orders with shipping status and amounts",
        "International sale Report": "Cross-border/export transactions",
        "Sale Report": "General retail sales data",
        "Cloud Warehouse Compersion Chart": "Warehouse metrics comparison",
        "Expense IIGF": "Expense tracking records",
        "P  L March 2021": "Profit & Loss statement",
        "May-2022": "Monthly operations data",
    }
    return fallbacks.get(table_name, "")


SCHEMA_TOOLS = [list_tables, get_table_schema, search_columns]
