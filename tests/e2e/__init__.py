"""End-to-end tests for the Retail Insights multi-agent workflow.

This package contains comprehensive E2E tests covering:
- Query workflow (test_queries.py): Complete query processing from NL to answer
- Summarization workflow (test_summarization.py): Summary and chat intent handling
- Error scenarios (test_error_scenarios.py): Graceful failure handling

Test fixtures are provided in conftest.py including:
- Sample retail sales data generation
- Mock LLM responses for deterministic testing
- FastAPI test client setup
"""
