"""Custom metrics for observability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram

_metrics: dict[str, Any] = {}


def get_meter(name: str = "retail_insights") -> Any:
    """Get an OpenTelemetry meter for custom metrics.

    Args:
        name: Meter name.

    Returns:
        OpenTelemetry meter instance.
    """
    try:
        from opentelemetry import metrics

        return metrics.get_meter(name)
    except ImportError:

        class NoOpMeter:
            def create_counter(self, name: str, **kwargs: Any) -> Any:
                return NoOpCounter()

            def create_histogram(self, name: str, **kwargs: Any) -> Any:
                return NoOpHistogram()

        return NoOpMeter()


class NoOpCounter:
    def add(self, amount: int, attributes: dict[str, str] | None = None) -> None:
        pass


class NoOpHistogram:
    def record(self, value: float, attributes: dict[str, str] | None = None) -> None:
        pass


def get_query_counter() -> Counter:
    """Get counter for tracking query counts."""
    if "query_counter" not in _metrics:
        meter = get_meter()
        _metrics["query_counter"] = meter.create_counter(
            "retail_insights.queries.total",
            description="Total number of queries processed",
            unit="1",
        )
    return _metrics["query_counter"]


def get_query_latency_histogram() -> Histogram:
    """Get histogram for tracking query latency."""
    if "query_latency" not in _metrics:
        meter = get_meter()
        _metrics["query_latency"] = meter.create_histogram(
            "retail_insights.queries.latency",
            description="Query processing latency",
            unit="ms",
        )
    return _metrics["query_latency"]


def get_llm_token_histogram() -> Histogram:
    """Get histogram for tracking LLM token usage."""
    if "llm_tokens" not in _metrics:
        meter = get_meter()
        _metrics["llm_tokens"] = meter.create_histogram(
            "retail_insights.llm.tokens",
            description="LLM token usage per request",
            unit="1",
        )
    return _metrics["llm_tokens"]


def record_query(intent: str, success: bool, duration_ms: float) -> None:
    """Record a query execution.

    Args:
        intent: Query intent type.
        success: Whether query succeeded.
        duration_ms: Query duration in milliseconds.
    """
    counter = get_query_counter()
    counter.add(1, {"intent": intent, "success": str(success)})

    histogram = get_query_latency_histogram()
    histogram.record(duration_ms, {"intent": intent})


def record_llm_usage(agent: str, tokens: int) -> None:
    """Record LLM token usage.

    Args:
        agent: Agent name (router, sql_generator, summarizer).
        tokens: Number of tokens used.
    """
    histogram = get_llm_token_histogram()
    histogram.record(tokens, {"agent": agent})
