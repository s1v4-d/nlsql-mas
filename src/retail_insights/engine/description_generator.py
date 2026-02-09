"""LLM-based table description generator with caching."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

if TYPE_CHECKING:
    from retail_insights.models.schema import TableSchema

logger = structlog.get_logger(__name__)

DESCRIPTION_CACHE_DIR = Path(".cache/table_descriptions")


class TableDescriptionResult(BaseModel):
    """LLM-generated table and column descriptions."""

    table_description: str = Field(
        description="One-sentence description of the table's purpose and content"
    )
    column_descriptions: dict[str, str] = Field(
        description="Brief description for each column explaining its meaning"
    )


DESCRIPTION_SYSTEM_PROMPT = """You are a database documentation expert.
Analyze the table schema and sample data to generate clear, concise descriptions.

Guidelines:
- Table description: One sentence explaining the table's business purpose
- Column descriptions: Brief phrase explaining what each column contains
- Infer meaning from column names, data types, and sample values
- Use domain terminology appropriate for retail/e-commerce data
- Be specific, avoid generic descriptions like "stores data"

Respond with JSON matching this exact structure:
{
    "table_description": "One sentence about the table",
    "column_descriptions": {
        "column_name": "Brief description",
        ...
    }
}"""

DESCRIPTION_USER_PROMPT = """Analyze this database table and generate descriptions.

Table: {table_name}
Row Count: {row_count:,}
{date_range_info}

Columns and Sample Values:
{columns_info}

Generate a business-focused description for this table and each column."""


class TableDescriptionGenerator:
    """Generates and caches table descriptions using LLM inference."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        cache_dir: Path | None = None,
    ):
        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
            api_key=SecretStr(api_key),
        )
        self.structured_llm = self.llm.with_structured_output(TableDescriptionResult)
        self.cache_dir = cache_dir or DESCRIPTION_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, TableDescriptionResult] = {}

    def get_description(
        self,
        table_name: str,
        schema: TableSchema,
        *,
        force_refresh: bool = False,
    ) -> TableDescriptionResult:
        """Get or generate cached description for a table."""
        cache_key = self._cache_key(table_name, schema)

        if not force_refresh and (cached := self._load_from_cache(cache_key)):
            logger.debug("description_cache_hit", table=table_name)
            return cached

        logger.info("generating_table_description", table=table_name)
        result = self._generate_description(table_name, schema)

        self._save_to_cache(cache_key, result)
        return result

    def _generate_description(
        self,
        table_name: str,
        schema: TableSchema,
    ) -> TableDescriptionResult:
        columns_info = self._format_columns_info(schema)

        date_range_info = ""
        if schema.date_range_start and schema.date_range_end:
            date_range_info = f"Date Range: {schema.date_range_start} to {schema.date_range_end}"

        user_prompt = DESCRIPTION_USER_PROMPT.format(
            table_name=table_name,
            row_count=schema.row_count or 0,
            date_range_info=date_range_info,
            columns_info=columns_info,
        )

        try:
            result = self.structured_llm.invoke(
                [
                    SystemMessage(content=DESCRIPTION_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ]
            )
            if not isinstance(result, TableDescriptionResult):
                return self._fallback_description(table_name, schema)
            return result
        except Exception as e:
            logger.error("description_generation_failed", table=table_name, error=str(e))
            return self._fallback_description(table_name, schema)

    def _format_columns_info(self, schema: TableSchema) -> str:
        lines = []
        for col in schema.columns:
            samples = ", ".join(str(s) for s in col.sample_values[:3]) if col.sample_values else "-"
            if len(samples) > 80:
                samples = samples[:77] + "..."
            lines.append(f"- {col.name} ({col.data_type}): {samples}")
        return "\n".join(lines)

    def _fallback_description(
        self,
        table_name: str,
        schema: TableSchema,
    ) -> TableDescriptionResult:
        table_desc = f"Data table containing {schema.row_count or 'unknown number of'} records"

        col_descs = {}
        for col in schema.columns:
            col_descs[col.name] = f"{col.data_type} column"

        return TableDescriptionResult(
            table_description=table_desc,
            column_descriptions=col_descs,
        )

    def _cache_key(self, table_name: str, schema: TableSchema) -> str:
        schema_str = f"{table_name}:{len(schema.columns)}:"
        schema_str += ",".join(f"{c.name}:{c.data_type}" for c in schema.columns)
        schema_hash = hashlib.md5(schema_str.encode(), usedforsecurity=False).hexdigest()[:12]
        return f"{table_name}_{schema_hash}"

    def _load_from_cache(self, cache_key: str) -> TableDescriptionResult | None:
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with cache_file.open() as f:
                    data = json.load(f)
                result = TableDescriptionResult(**data)
                self._memory_cache[cache_key] = result
                return result
            except Exception as e:
                logger.warning("cache_load_failed", key=cache_key, error=str(e))

        return None

    def _save_to_cache(self, cache_key: str, result: TableDescriptionResult) -> None:
        self._memory_cache[cache_key] = result

        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with cache_file.open("w") as f:
                json.dump(result.model_dump(), f, indent=2)
        except Exception as e:
            logger.warning("cache_save_failed", key=cache_key, error=str(e))


_generator: TableDescriptionGenerator | None = None


def get_description_generator() -> TableDescriptionGenerator:
    global _generator
    if _generator is None:
        from retail_insights.core.config import get_settings

        settings = get_settings()
        _generator = TableDescriptionGenerator(
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            model=settings.OPENAI_MODEL,
        )
    return _generator


async def generate_table_description(
    table_name: str,
    schema: TableSchema,
) -> TableDescriptionResult:
    generator = get_description_generator()
    return generator.get_description(table_name, schema)
